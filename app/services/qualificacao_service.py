from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.cadencia import Cadencia
from app.models.configuracao_qualificacao import ConfiguracaoQualificacao
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.decisor import Decisor
from app.models.faq_item import FaqItem
from app.models.mensagem import Mensagem
from app.models.turno_conversa import TurnoConversa
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.services import auditoria_service, cadencia_service, faq_service, notificacao_service, scoring_service
from app.services.errors import NaoEncontrado

_PREFIXO_CONTINUAR = "CONTINUAR:"
_PREFIXO_TRANSFERIR = "TRANSFERIR:"
_PREFIXO_FAQ = "FAQ:"


def _limiar(db: Session, tenant_id: str) -> float:
    config = db.query(ConfiguracaoQualificacao).filter_by(tenant_id=tenant_id).one_or_none()
    return config.limiar_padrao if config else settings.limiar_qualificacao_padrao


def _obter_ou_iniciar_conversa(
    db: Session, tenant_id: str, conta_id: int, decisor_id: int, canal: str
) -> ConversaQualificacao:
    conversa = (
        db.query(ConversaQualificacao)
        .filter_by(tenant_id=tenant_id, decisor_id=decisor_id, status="em_andamento")
        .order_by(ConversaQualificacao.id.desc())
        .first()
    )
    if conversa is not None:
        return conversa

    conversa = ConversaQualificacao(
        tenant_id=tenant_id,
        conta_id=conta_id,
        decisor_id=decisor_id,
        canal=canal,
        etapa_atual=scoring_service.ETAPAS[0],
        status="em_andamento",
    )
    db.add(conversa)
    db.flush()
    return conversa


def obter_com_turnos(db: Session, tenant_id: str, conversa_id: int) -> tuple[ConversaQualificacao, list[TurnoConversa]]:
    conversa = db.query(ConversaQualificacao).filter_by(id=conversa_id, tenant_id=tenant_id).one_or_none()
    if conversa is None:
        raise NaoEncontrado(f"Conversa {conversa_id} não encontrada")
    turnos = (
        db.query(TurnoConversa).filter_by(conversa_id=conversa.id).order_by(TurnoConversa.criado_em).all()
    )
    return conversa, turnos


def processar_mensagem_recebida(
    db: Session,
    tenant_id: str,
    decisor_id: int,
    canal: str,
    texto: str,
    llm: LLMProvider,
    whatsapp: WhatsAppProvider,
) -> dict:
    """Ponto de entrada único, chamado pelos webhooks de resposta (Onda 2).

    Roteiro de qualificação S.H.A.R.K. adaptativo às respostas (E5-H1).
    Contrato estrito com o LLM: toda resposta começa com `CONTINUAR:` (segue
    o roteiro) ou `TRANSFERIR:` (fora do roteiro). Sem prefixo reconhecido,
    o padrão é transferir — nunca inventa uma resposta fora da base.
    """
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    conversa = _obter_ou_iniciar_conversa(db, tenant_id, decisor.conta_id, decisor.id, canal)
    db.add(TurnoConversa(tenant_id=tenant_id, conversa_id=conversa.id, direcao="entrada", conteudo=texto))
    db.flush()

    faqs = faq_service.listar(db, tenant_id)
    bloco_faq = (
        "\n\nPerguntas frequentes cadastradas (responda com o número exato se a mensagem do lead "
        "corresponder a uma delas):\n" + "\n".join(f"{i + 1}. {item.pergunta}" for i, item in enumerate(faqs))
        if faqs
        else ""
    )

    resposta = llm.generate(
        LLMRequest(
            prompt=(
                "Você conduz uma qualificação de vendas pelo método S.H.A.R.K. "
                f"Etapa atual do roteiro: '{conversa.etapa_atual}'. Responda SEMPRE começando com "
                f"'{_PREFIXO_CONTINUAR}' seguido da próxima pergunta do roteiro, "
                f"'{_PREFIXO_FAQ}' seguido do número da pergunta frequente correspondente, ou "
                f"'{_PREFIXO_TRANSFERIR}' seguido do motivo, caso a mensagem do lead esteja fora do "
                "roteiro e fora da base de perguntas frequentes — nunca invente informação fora do "
                f"roteiro ou da base.{bloco_faq}\n\n"
                f"Mensagem do lead: {texto}"
            )
        )
    )

    if resposta.content.startswith(_PREFIXO_FAQ):
        return _responder_faq(db, tenant_id, conversa, decisor, canal, resposta.content, faqs, whatsapp)

    pode_continuar = resposta.content.startswith(_PREFIXO_CONTINUAR) and conversa.etapa_atual != "concluida"
    if pode_continuar:
        return _continuar_roteiro(db, tenant_id, conversa, decisor, canal, resposta.content, whatsapp)
    return _transferir_para_humano(db, tenant_id, conversa, decisor, canal, resposta.content, whatsapp)


def _continuar_roteiro(
    db: Session,
    tenant_id: str,
    conversa: ConversaQualificacao,
    decisor: Decisor,
    canal: str,
    conteudo_llm: str,
    whatsapp: WhatsAppProvider,
) -> dict:
    conteudo_saida = conteudo_llm[len(_PREFIXO_CONTINUAR) :].strip()
    db.add(TurnoConversa(tenant_id=tenant_id, conversa_id=conversa.id, direcao="saida", conteudo=conteudo_saida))

    indice_atual = scoring_service.ETAPAS.index(conversa.etapa_atual)
    proxima_etapa = (
        scoring_service.ETAPAS[indice_atual + 1] if indice_atual + 1 < len(scoring_service.ETAPAS) else "concluida"
    )
    conversa.etapa_atual = proxima_etapa
    if proxima_etapa == "concluida":
        conversa.status = "concluida"
    db.flush()

    limiar = _limiar(db, tenant_id)
    score = scoring_service.recalcular_e_salvar(db, tenant_id, conversa, limiar)

    notificacao_id = None
    if score.score_total >= limiar:
        notificacao = notificacao_service.notificar_vendedor(
            db, tenant_id, conversa, whatsapp, motivo="limiar de qualificação atingido"
        )
        notificacao_id = notificacao.id

    auditoria_service.registrar(
        db,
        tenant_id,
        "qualificacao_avancou",
        "conversa_qualificacao",
        conversa.id,
        None,
        {"etapa": proxima_etapa, "score_total": score.score_total},
        conta_id=decisor.conta_id,
        canal=canal,
    )
    db.commit()
    return {
        "conversa_id": conversa.id,
        "status": conversa.status,
        "etapa_atual": conversa.etapa_atual,
        "score_total": score.score_total,
        "transferido": False,
        "notificacao_id": notificacao_id,
        "faq_respondida": False,
    }


def _transferir_para_humano(
    db: Session,
    tenant_id: str,
    conversa: ConversaQualificacao,
    decisor: Decisor,
    canal: str,
    conteudo_llm: str,
    whatsapp: WhatsAppProvider,
) -> dict:
    motivo = (
        conteudo_llm[len(_PREFIXO_TRANSFERIR) :].strip()
        if conteudo_llm.startswith(_PREFIXO_TRANSFERIR)
        else "resposta fora do roteiro de qualificação"
    )
    conversa.status = "transferida_humano"
    conversa.transferido_em = datetime.now(UTC)
    db.flush()

    notificacao = notificacao_service.notificar_vendedor(db, tenant_id, conversa, whatsapp, motivo=motivo)

    auditoria_service.registrar(
        db,
        tenant_id,
        "qualificacao_transferida",
        "conversa_qualificacao",
        conversa.id,
        None,
        {"motivo": motivo},
        conta_id=decisor.conta_id,
        canal=canal,
    )
    db.commit()
    return {
        "conversa_id": conversa.id,
        "status": conversa.status,
        "etapa_atual": conversa.etapa_atual,
        "score_total": None,
        "transferido": True,
        "notificacao_id": notificacao.id,
        "faq_respondida": False,
    }


def _responder_faq(
    db: Session,
    tenant_id: str,
    conversa: ConversaQualificacao,
    decisor: Decisor,
    canal: str,
    conteudo_llm: str,
    faqs: list[FaqItem],
    whatsapp: WhatsAppProvider,
) -> dict:
    """Responde com o texto armazenado na base de FAQ — nunca com texto
    gerado pelo LLM (E5-H4). Se o número referenciado não existir na base
    carregada, cai no mesmo fail-safe de transferência do contrato
    CONTINUAR:/TRANSFERIR: — nunca inventa."""
    numero = conteudo_llm[len(_PREFIXO_FAQ) :].strip()
    item = None
    if numero.isdigit():
        indice = int(numero) - 1
        if 0 <= indice < len(faqs):
            item = faqs[indice]

    if item is None:
        return _transferir_para_humano(
            db, tenant_id, conversa, decisor, canal, "TRANSFERIR: pergunta não localizada na base de FAQ", whatsapp
        )

    db.add(TurnoConversa(tenant_id=tenant_id, conversa_id=conversa.id, direcao="saida", conteudo=item.resposta))

    auditoria_service.registrar(
        db,
        tenant_id,
        "faq_respondida",
        "conversa_qualificacao",
        conversa.id,
        None,
        {"faq_id": item.id},
        conta_id=decisor.conta_id,
        canal=canal,
    )
    db.commit()
    return {
        "conversa_id": conversa.id,
        "status": conversa.status,
        "etapa_atual": conversa.etapa_atual,
        "score_total": None,
        "transferido": False,
        "notificacao_id": None,
        "faq_respondida": True,
    }


def devolver(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    decisor_id: int,
    motivo: str,
    cadencia_nutricao_id: int,
    llm: LLMProvider,
) -> dict:
    """Devolve o lead à cadência de nutrição adequada ao motivo (E7-H2).

    Histórico preservado; mensagens ainda pendentes da conversa/cadência
    anterior são canceladas antes de entrar na nutrição, para não duplicar.
    """
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    cadencia_nutricao = (
        db.query(Cadencia)
        .filter_by(id=cadencia_nutricao_id, tenant_id=tenant_id, tipo="nutricao")
        .one_or_none()
    )
    if cadencia_nutricao is None:
        raise NaoEncontrado(f"Cadência de nutrição {cadencia_nutricao_id} não encontrada")

    conversa = (
        db.query(ConversaQualificacao)
        .filter_by(tenant_id=tenant_id, decisor_id=decisor.id, status="em_andamento")
        .order_by(ConversaQualificacao.id.desc())
        .first()
    )
    if conversa is not None:
        conversa.status = "devolvida"
        conversa.motivo_devolucao = motivo

    pendentes = (
        db.query(Mensagem)
        .filter(Mensagem.decisor_id == decisor.id, Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]))
        .all()
    )
    for mensagem in pendentes:
        mensagem.status = "cancelado"
    db.flush()

    resultado_geracao = cadencia_service.gerar_para_lote(
        db, tenant_id, ator_id, cadencia_nutricao.id, [decisor.conta_id], llm
    )

    auditoria_service.registrar(
        db,
        tenant_id,
        "lead_devolvido",
        "decisor",
        decisor.id,
        ator_id,
        {"motivo": motivo, "cadencia_nutricao_id": cadencia_nutricao.id, "mensagens_canceladas": len(pendentes)},
        conta_id=decisor.conta_id,
    )
    db.commit()

    return {
        "decisor_id": decisor.id,
        "cadencia_nutricao_id": cadencia_nutricao.id,
        "mensagens_canceladas": len(pendentes),
        **resultado_geracao,
    }
