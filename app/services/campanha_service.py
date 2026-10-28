import hashlib
import hmac
import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.texto import corrigir_codificacao
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.campanha import DestinatarioAvulsoSchema
from app.services import (
    atividade_service,
    auditoria_service,
    bloqueio_contato_service,
    campanha_personalizacao,
    limite_criacao_service,
    optout_service,
    rastreamento_service,
    reputacao_service,
)
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

logger = logging.getLogger(__name__)

_SEPARADOR = ":"
_RESERVA_MINUTOS = 10

_REMETENTE_NOME = "B2B ON"

# Formato mínimo de um endereço (algo@dominio.ext, sem espaços): barra o que não é e-mail antes de chegar ao servidor ("https://linkedin.com/in/...", "SM",
# lista de certificações) — colunas deslocadas numa planilha colada põem esse tipo de texto no campo de e-mail.
_EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email_valido(email: str | None) -> bool:
    return bool(email) and _EMAIL_VALIDO.match(email.strip()) is not None


def _emails_devolvidos(db: Session, tenant_id: str) -> set[str]:
    """Endereços que já voltaram como não entregues (aviso do provedor ou registro manual) em campanhas ou cadências do tenant."""
    de_campanhas = db.query(func.lower(CampanhaDestinatario.email)).filter(
        CampanhaDestinatario.tenant_id == tenant_id, CampanhaDestinatario.bounce_em.isnot(None), CampanhaDestinatario.email.isnot(None)
    )
    de_cadencias = (
        db.query(func.lower(Decisor.email))
        .join(Mensagem, Mensagem.decisor_id == Decisor.id)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.bounce_em.isnot(None), Decisor.email.isnot(None))
    )
    return {email for (email,) in [*de_campanhas.all(), *de_cadencias.all()]}


def _motivo_sem_destino(
    campanha: Campanha,
    destinatario: CampanhaDestinatario,
    devolvidos: set[str] | None = None,
    bloqueados: bloqueio_contato_service.Bloqueados | None = None,
) -> str | None:
    """Motivo pelo qual não existe para onde enviar nos canais da campanha (e-mail que não é e-mail e sem telefone/template de WhatsApp), ou `None`
    se há ao menos um destino. Esse destinatário vira `nao_enviado`, nunca `falhou`: não houve tentativa, então não entra em retentativa nem em bounce."""
    if bloqueados is not None and bloqueados.contem(destinatario.email, destinatario.telefone):
        return "Pediu para não receber (lista de bloqueio da empresa)."  # vale para todos os canais: quem pediu não recebe por e-mail nem por WhatsApp
    devolvido = bool(destinatario.email) and destinatario.email.strip().lower() in (devolvidos or set())
    tem_email = "email" in campanha.canais and _email_valido(destinatario.email) and not devolvido
    tem_whatsapp = "whatsapp" in campanha.canais and bool(destinatario.telefone) and bool(campanha.template_whatsapp_id)
    if tem_email or tem_whatsapp:
        return None
    if "email" in campanha.canais and destinatario.email:
        if devolvido:
            return f"E-mail devolvido em envio anterior: {destinatario.email.strip()[:80]}"  # não insiste em endereço que já voltou
        return f"E-mail inválido: {destinatario.email.strip()[:80]}"
    return "Sem e-mail ou telefone compatível com os canais da campanha."


def _validar_canais(canais: list[str], assunto: str | None, conteudo_email: str | None, template_whatsapp_id: str | None) -> None:
    if not canais:
        raise ValidacaoFalhou("Selecione ao menos um canal (e-mail e/ou WhatsApp).")
    if "email" in canais and not (assunto and conteudo_email):
        raise ValidacaoFalhou("Campanhas com canal e-mail exigem assunto e conteúdo.")
    if "whatsapp" in canais and not template_whatsapp_id:
        raise ValidacaoFalhou("Campanhas com canal WhatsApp exigem um template aprovado pela Meta.")


def criar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    nome: str,
    tipo: str,
    canais: list[str],
    assunto: str | None,
    conteudo_email: str | None,
    template_whatsapp_id: str | None,
    plan_limits: PlanLimitsProvider,
) -> Campanha:
    limite_criacao_service.verificar_limite_campanhas(db, tenant_id, plan_limits)
    _validar_canais(canais, assunto, conteudo_email, template_whatsapp_id)
    campanha = Campanha(
        tenant_id=tenant_id,
        nome=nome,
        tipo=tipo,
        canais=canais,
        assunto=assunto,
        conteudo_email=conteudo_email,
        template_whatsapp_id=template_whatsapp_id,
        status="rascunho",
    )
    db.add(campanha)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "campanha_criada", "campanha", campanha.id, ator_id, {"nome": nome})
    db.commit()
    db.refresh(campanha)
    return campanha


def obter(db: Session, tenant_id: str, campanha_id: int) -> Campanha:
    campanha = db.query(Campanha).filter_by(id=campanha_id, tenant_id=tenant_id).one_or_none()
    if campanha is None:
        raise NaoEncontrado(f"Campanha {campanha_id} não encontrada")
    return campanha


def listar(db: Session, tenant_id: str) -> list[Campanha]:
    return db.query(Campanha).filter_by(tenant_id=tenant_id).order_by(Campanha.criado_em.desc()).all()


def _exigir_rascunho(campanha: Campanha) -> None:
    if campanha.status != "rascunho":
        raise RegraNegocioViolada("Essa ação só é permitida enquanto a campanha está em rascunho.")


def atualizar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    campanha_id: int,
    nome: str,
    tipo: str,
    canais: list[str],
    assunto: str | None,
    conteudo_email: str | None,
    template_whatsapp_id: str | None,
) -> Campanha:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    _validar_canais(canais, assunto, conteudo_email, template_whatsapp_id)
    campanha.nome = nome
    campanha.tipo = tipo
    campanha.canais = canais
    campanha.assunto = assunto
    campanha.conteudo_email = conteudo_email
    campanha.template_whatsapp_id = template_whatsapp_id
    auditoria_service.registrar(db, tenant_id, "campanha_atualizada", "campanha", campanha.id, ator_id, {})
    db.commit()
    db.refresh(campanha)
    return campanha


def excluir(db: Session, tenant_id: str, ator_id: str | None, campanha_id: int) -> None:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).delete()
    db.delete(campanha)
    auditoria_service.registrar(db, tenant_id, "campanha_excluida", "campanha", campanha_id, ator_id, {})
    db.commit()


def listar_destinatarios(db: Session, tenant_id: str, campanha_id: int) -> list[CampanhaDestinatario]:
    obter(db, tenant_id, campanha_id)
    return (
        db.query(CampanhaDestinatario)
        .filter_by(campanha_id=campanha_id)
        .order_by(CampanhaDestinatario.id)
        .all()
    )


def metricas(db: Session, tenant_id: str, campanha_id: int) -> dict[str, int]:
    destinatarios = listar_destinatarios(db, tenant_id, campanha_id)
    contagem = {"total": len(destinatarios), "pendente": 0, "enviado": 0, "falhou": 0, "nao_enviado": 0, "optout": 0}
    for destinatario in destinatarios:
        contagem[destinatario.status] = contagem.get(destinatario.status, 0) + 1
    return contagem


def adicionar_de_decisores(
    db: Session, tenant_id: str, ator_id: str | None, campanha_id: int, decisor_ids: list[int]
) -> list[CampanhaDestinatario]:
    """Snapshot de nome/e-mail/telefone no momento em que entra na
    campanha — pula quem já está suprimido (opt-out), reaproveitando a
    mesma lista de supressão que protege a cadência (E9-H2)."""
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)

    ja_adicionados = {
        destinatario.decisor_id
        for destinatario in db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).all()
        if destinatario.decisor_id is not None
    }

    adicionados: list[CampanhaDestinatario] = []
    for decisor_id in decisor_ids:
        if decisor_id in ja_adicionados:
            continue
        decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
        if decisor is None or optout_service.existe_supressao(db, decisor.id):
            continue
        if decisor.email and not _email_valido(decisor.email) and not decisor.telefone:
            continue  # o único contato cadastrado não é um e-mail (ex.: link): não há como enviar
        conta = db.query(Conta).filter_by(id=decisor.conta_id, tenant_id=tenant_id).one_or_none()
        destinatario = CampanhaDestinatario(
            tenant_id=tenant_id,
            campanha_id=campanha.id,
            decisor_id=decisor.id,
            nome=decisor.nome,
            email=decisor.email,
            telefone=decisor.telefone,
            empresa=(conta.nome_fantasia or conta.nome) if conta is not None else None,
        )
        db.add(destinatario)
        adicionados.append(destinatario)
        ja_adicionados.add(decisor_id)

    db.flush()
    auditoria_service.registrar(
        db,
        tenant_id,
        "campanha_destinatarios_adicionados",
        "campanha",
        campanha.id,
        ator_id,
        {"quantidade": len(adicionados), "origem": "decisores"},
    )
    db.commit()
    for destinatario in adicionados:
        db.refresh(destinatario)
    return adicionados


def adicionar_avulsos(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    campanha_id: int,
    destinatarios: list[DestinatarioAvulsoSchema],
) -> list[CampanhaDestinatario]:
    """Lista colada/avulsa — sem Decisor de origem, então sem checagem
    contra a supressão do CRM (limitação documentada: um destinatário
    avulso que se descadastra só fica suprimido dentro desta campanha,
    não em campanhas futuras — não existe hoje uma lista de supressão
    por e-mail cruzando campanhas)."""
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)

    ja_existentes = {
        destinatario.email.strip().lower()
        for destinatario in db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).all()
        if destinatario.email
    }

    adicionados: list[CampanhaDestinatario] = []
    corrigidos = 0
    for item in destinatarios:
        # Texto colado de planilha aberta com a codificação errada ("JoÃ£o") é consertado na entrada, para o e-mail não sair com o nome estragado.
        nome = (corrigir_codificacao(item.nome) or "").strip()
        telefone = (corrigir_codificacao(item.telefone) or "").strip() or None
        empresa = (corrigir_codificacao(item.empresa) or "").strip() or None
        corrigidos += (nome, telefone, empresa) != (item.nome.strip(), (item.telefone or "").strip() or None, (item.empresa or "").strip() or None)
        email = (item.email or "").strip() or None
        if email and not _email_valido(email):
            email = None  # não é um e-mail (link, sigla, certificações): não entra como endereço de envio
        if not nome or not (email or telefone):
            continue
        if email and email.lower() in ja_existentes:
            continue
        destinatario = CampanhaDestinatario(
            tenant_id=tenant_id, campanha_id=campanha.id, decisor_id=None, nome=nome, email=email, telefone=telefone, empresa=empresa
        )
        db.add(destinatario)
        adicionados.append(destinatario)
        if email:
            ja_existentes.add(email.lower())

    db.flush()
    auditoria_service.registrar(
        db,
        tenant_id,
        "campanha_destinatarios_adicionados",
        "campanha",
        campanha.id,
        ator_id,
        {"quantidade": len(adicionados), "origem": "avulso", "codificacao_corrigida": corrigidos},
    )
    db.commit()
    for destinatario in adicionados:
        db.refresh(destinatario)
    return adicionados


def remover_destinatario(db: Session, tenant_id: str, ator_id: str | None, campanha_id: int, destinatario_id: int) -> None:
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    destinatario = (
        db.query(CampanhaDestinatario)
        .filter_by(id=destinatario_id, campanha_id=campanha.id, tenant_id=tenant_id)
        .one_or_none()
    )
    if destinatario is None:
        raise NaoEncontrado(f"Destinatário {destinatario_id} não encontrado")
    db.delete(destinatario)
    auditoria_service.registrar(
        db, tenant_id, "campanha_destinatario_removido", "campanha", campanha.id, ator_id, {"destinatario_id": destinatario_id}
    )
    db.commit()


def _obter_destinatario(db: Session, tenant_id: str, campanha_id: int, destinatario_id: int) -> CampanhaDestinatario:
    destinatario = (
        db.query(CampanhaDestinatario).filter_by(id=destinatario_id, campanha_id=campanha_id, tenant_id=tenant_id).one_or_none()
    )
    if destinatario is None:
        raise NaoEncontrado(f"Destinatário {destinatario_id} não encontrado")
    return destinatario


def editar_destinatario(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    campanha_id: int,
    destinatario_id: int,
    nome: str,
    email: str | None,
    telefone: str | None,
    empresa: str | None,
    reenviar: bool = False,
    atualizar_contato_crm: bool = False,
) -> CampanhaDestinatario:
    """Corrige os dados de um destinatário (ex.: o contato avisou que trocou de e-mail). Só com a campanha parada (rascunho ou concluída). Trocar o e-mail:
    zera o que pertencia ao endereço antigo (entrega, abertura, bounce); quem ainda não tinha recebido (não enviado ou falha) volta para a fila, e quem já
    recebeu só troca com `reenviar` (senão o histórico passaria a dizer que o novo endereço recebeu o que não recebeu). Se a campanha estava concluída e o
    destinatário volta para a fila, a campanha volta ao rascunho para o envio poder ser retomado."""
    campanha = obter(db, tenant_id, campanha_id)
    if campanha.status in ("pronta", "enviando"):
        raise RegraNegocioViolada("A campanha está sendo enviada. Espere terminar, ou volte a campanha para rascunho, para editar destinatários.")
    destinatario = _obter_destinatario(db, tenant_id, campanha_id, destinatario_id)

    nome_novo = (corrigir_codificacao(nome) or "").strip()
    if not nome_novo:
        raise ValidacaoFalhou("Informe o nome do destinatário.")
    email_novo = (email or "").strip() or None
    if email_novo and not _email_valido(email_novo):
        raise ValidacaoFalhou("Informe um e-mail válido (algo@empresa.com.br) ou deixe o campo em branco.")
    telefone_novo = (corrigir_codificacao(telefone) or "").strip() or None
    empresa_nova = (corrigir_codificacao(empresa) or "").strip() or None
    if not (email_novo or telefone_novo):
        raise ValidacaoFalhou("Informe ao menos o e-mail ou o telefone.")

    email_antigo = (destinatario.email or "").strip().lower()
    email_mudou = (email_novo or "").lower() != email_antigo
    if email_mudou and email_novo:
        repetido = (
            db.query(CampanhaDestinatario)
            .filter(
                CampanhaDestinatario.campanha_id == campanha_id,
                CampanhaDestinatario.id != destinatario.id,
                func.lower(CampanhaDestinatario.email) == email_novo.lower(),
            )
            .first()
        )
        if repetido is not None:
            raise ValidacaoFalhou("Já existe outro destinatário com este e-mail nesta campanha.")
    if email_mudou and destinatario.status == "enviado" and not reenviar:
        raise ValidacaoFalhou(
            "Este e-mail já recebeu a campanha. Para trocar o endereço, marque “Enviar a campanha também para o novo e-mail”."
        )
    if email_mudou and destinatario.status == "optout":
        raise ValidacaoFalhou("Este contato pediu para não receber. Para voltar a enviar, remova-o da lista de bloqueio.")

    destinatario.nome = nome_novo
    destinatario.email = email_novo
    destinatario.telefone = telefone_novo
    destinatario.empresa = empresa_nova

    volta_para_a_fila = False
    if email_mudou:
        destinatario.bounce_em = None
        destinatario.motivo_bounce = None
        destinatario.entregue_em = None
        destinatario.aberto_em = None
        destinatario.pixel_incluido = False
        destinatario.motivo_falha = None
        if destinatario.status in ("enviado", "falhou", "nao_enviado"):
            destinatario.status = "pendente"
            destinatario.enviado_em = None
            volta_para_a_fila = True
        if atualizar_contato_crm and destinatario.decisor_id is not None and email_novo:
            decisor = db.query(Decisor).filter_by(id=destinatario.decisor_id, tenant_id=tenant_id).one_or_none()
            if decisor is not None:
                decisor.email = email_novo

    auditoria_service.registrar(
        db, tenant_id, "campanha_destinatario_editado", "campanha", campanha_id, ator_id,
        {"destinatario_id": destinatario.id, "email_mudou": email_mudou, "reenviar": reenviar, "contato_crm_atualizado": bool(atualizar_contato_crm and email_mudou)},
    )
    db.commit()
    if volta_para_a_fila and campanha.status == "concluida":
        voltar_para_rascunho(db, tenant_id, ator_id, campanha_id)
    db.refresh(destinatario)
    return destinatario


def nao_quer_receber(
    db: Session, tenant_id: str, ator_id: str | None, campanha_id: int, destinatario_id: int, motivo: str | None = None
) -> CampanhaDestinatario:
    """O contato disse que não quer receber (e não clicou em cancelar): fica `optout` nesta campanha e o e-mail e o telefone entram na lista de bloqueio da
    empresa, que vale para todas as campanhas. Se veio do CRM, aplica o cancelamento completo do contato (supressão, cadências pendentes). Pode ser feito com a
    campanha em qualquer estado: o envio em andamento pula quem deixou de estar pendente."""
    obter(db, tenant_id, campanha_id)
    destinatario = _obter_destinatario(db, tenant_id, campanha_id, destinatario_id)
    texto = (motivo or "").strip() or "Informado manualmente: não quer receber."

    destinatario.status = "optout"
    destinatario.motivo_falha = texto
    bloqueio_contato_service.registrar(
        db, tenant_id, ator_id, email=destinatario.email, telefone=destinatario.telefone, motivo=texto, origem="campanha"
    )
    if destinatario.decisor_id is not None:
        decisor = db.query(Decisor).filter_by(id=destinatario.decisor_id, tenant_id=tenant_id).one_or_none()
        if decisor is not None:
            optout_service.aplicar(db, tenant_id, decisor, origem="campanha_manual")
    auditoria_service.registrar(
        db, tenant_id, "campanha_destinatario_nao_quer_receber", "campanha", campanha_id, ator_id, {"destinatario_id": destinatario.id}
    )
    db.commit()
    db.refresh(destinatario)
    return destinatario


def marcar_pronta(
    db: Session, tenant_id: str, ator_id: str | None, campanha_id: int, destinatario_ids: list[int] | None = None
) -> Campanha:
    """Sem `destinatario_ids` envia a todos os `pendente` (quem falhou antes é tentado de novo; quem já recebeu nunca é reenviado). Com a lista, envia só a
    esses (ex.: um teste com poucos): os demais `pendente` ficam `retido` até o fim desta rodada, quando voltam a `pendente` e a campanha volta ao rascunho
    (`_enviar_pendentes`) — assim nem o envio imediato nem o agendador de reserva os alcançam enquanto a rodada dura."""
    campanha = obter(db, tenant_id, campanha_id)
    _exigir_rascunho(campanha)
    if "email" in campanha.canais:
        reputacao_service.exigir_canal_nao_pausado(db, tenant_id, "email")
    total = db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id).count()
    if total == 0:
        raise ValidacaoFalhou("Adicione ao menos um destinatário antes de marcar a campanha como pronta.")
    _validar_canais(campanha.canais, campanha.assunto, campanha.conteudo_email, campanha.template_whatsapp_id)

    do_envio = db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id, tenant_id=tenant_id)
    elegiveis = {
        i: status
        for i, status in do_envio.filter(CampanhaDestinatario.status.in_(["pendente", "falhou"]))
        .with_entities(CampanhaDestinatario.id, CampanhaDestinatario.status)
        .all()
    }
    retidos: list[int] = []
    if destinatario_ids is None:
        escolhidos = set(elegiveis)
    else:
        escolhidos = set(destinatario_ids) & set(elegiveis)
        retidos = [i for i, status in elegiveis.items() if status == "pendente" and i not in escolhidos]
    if not escolhidos:
        raise ValidacaoFalhou(
            "Selecione ao menos um destinatário que ainda não recebeu."
            if destinatario_ids is not None
            else "Todos os destinatários já receberam esta campanha."
        )
    refazer = [i for i in escolhidos if elegiveis[i] == "falhou"]
    if refazer:
        do_envio.filter(CampanhaDestinatario.id.in_(refazer)).update(
            {"status": "pendente", "motivo_falha": None}, synchronize_session=False
        )
    if retidos:
        do_envio.filter(CampanhaDestinatario.id.in_(retidos)).update({"status": "retido"}, synchronize_session=False)
    campanha.status = "pronta"
    auditoria_service.registrar(
        db, tenant_id, "campanha_marcada_pronta", "campanha", campanha.id, ator_id,
        {"destinatarios": len(escolhidos), "retidos": len(retidos)},
    )
    db.commit()
    db.refresh(campanha)
    return campanha


def voltar_para_rascunho(db: Session, tenant_id: str, ator_id: str | None, campanha_id: int) -> Campanha:
    """Devolve a campanha ao rascunho para o conteúdo ser editado antes de (re)enviar. Quem já recebeu continua `enviado` e não recebe de novo; os
    que falharam voltam à fila (`pendente`). Um envio em andamento para no destinatário seguinte."""
    campanha = obter(db, tenant_id, campanha_id)
    if campanha.status == "rascunho":
        return campanha
    db.query(CampanhaDestinatario).filter(
        CampanhaDestinatario.campanha_id == campanha.id,
        CampanhaDestinatario.tenant_id == tenant_id,
        CampanhaDestinatario.status.in_(["falhou", "retido"]),
    ).update({"status": "pendente", "motivo_falha": None}, synchronize_session=False)
    campanha.status = "rascunho"
    campanha.processando_ate = None
    auditoria_service.registrar(db, tenant_id, "campanha_voltou_para_rascunho", "campanha", campanha.id, ator_id, {})
    db.commit()
    db.refresh(campanha)
    return campanha


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _reservar_disparo(db: Session, campanha_id: int) -> bool:
    """Reserva atômica da campanha: só um processo envia por vez (o envio imediato e o agendador podem coincidir). A reserva vence sozinha em
    `_RESERVA_MINUTOS`, então um processo que caiu no meio não trava a campanha — o ciclo seguinte continua de onde parou."""
    agora = _agora()
    reservada = (
        db.query(Campanha)
        .filter(
            Campanha.id == campanha_id,
            Campanha.status.in_(["pronta", "enviando"]),
            or_(Campanha.processando_ate.is_(None), Campanha.processando_ate < agora),
        )
        .update({"status": "enviando", "processando_ate": agora + timedelta(minutes=_RESERVA_MINUTOS)}, synchronize_session=False)
    )
    db.commit()
    return bool(reservada)


def processar_pendentes(
    db: Session, tenant_id: str, email_provider: EmailProvider, whatsapp_provider: WhatsAppProvider, campanha_id: int | None = None
) -> dict:
    """Dispatcher chamado logo após "Marcar como pronta" (em segundo plano, com `campanha_id`) e pelo cron externo (todas as campanhas do tenant;
    mesmo padrão síncrono e idempotente de `envio_service.processar_pendentes`). Cada destinatário `pendente` é disparado e gravado na hora (um commit
    por destinatário): se o processo cair no meio, ninguém que já recebeu volta a ser enviado, e a reserva da campanha vence sozinha para o ciclo
    seguinte continuar. Ao esgotar os pendentes, a campanha vira `concluida`."""
    resultado = {"enviadas": 0, "falhas": 0, "adiadas": 0}

    consulta = db.query(Campanha.id).filter(Campanha.tenant_id == tenant_id, Campanha.status.in_(["pronta", "enviando"]))
    if campanha_id is not None:
        consulta = consulta.filter(Campanha.id == campanha_id)
    for (id_da_campanha,) in consulta.order_by(Campanha.id).all():
        if not _reservar_disparo(db, id_da_campanha):
            continue  # outro processo está enviando esta campanha agora
        try:
            _enviar_pendentes(db, tenant_id, id_da_campanha, email_provider, whatsapp_provider, resultado)
        except Exception:
            db.rollback()
            db.query(Campanha).filter_by(id=id_da_campanha).update({"processando_ate": None}, synchronize_session=False)
            db.commit()
            raise
    return resultado


def _enviar_pendentes(
    db: Session, tenant_id: str, campanha_id: int, email_provider: EmailProvider, whatsapp_provider: WhatsAppProvider, resultado: dict
) -> None:
    campanha = db.query(Campanha).filter_by(id=campanha_id, tenant_id=tenant_id).one()
    ids_pendentes = [
        i for (i,) in db.query(CampanhaDestinatario.id).filter_by(campanha_id=campanha_id, tenant_id=tenant_id, status="pendente")
        .order_by(CampanhaDestinatario.id).all()
    ]
    algum_adiado = False
    interrompido = False
    devolvidos = _emails_devolvidos(db, tenant_id)
    bloqueados = bloqueio_contato_service.carregar(db, tenant_id)
    for destinatario_id in ids_pendentes:
        db.refresh(campanha)
        if campanha.status not in ("pronta", "enviando"):
            break  # a campanha voltou ao rascunho (edição) durante o envio: para sem mexer no que o usuário acabou de ajustar
        destinatario = db.get(CampanhaDestinatario, destinatario_id)
        if destinatario is None or destinatario.status != "pendente":
            continue  # saiu da lista (descadastro, remoção) desde a consulta
        motivo_ignorado = _motivo_sem_destino(campanha, destinatario, devolvidos, bloqueados)
        if motivo_ignorado is not None:
            destinatario.status = "nao_enviado"  # sem tentativa: nem falha, nem retentativa, nem bounce
            destinatario.motivo_falha = motivo_ignorado
            resultado["ignoradas"] = resultado.get("ignoradas", 0) + 1
            campanha.processando_ate = _agora() + timedelta(minutes=_RESERVA_MINUTOS)
            db.commit()
            continue
        sucesso, motivo_falha, adiado = _disparar_destinatario(db, campanha, destinatario, email_provider, whatsapp_provider)
        if sucesso:
            destinatario.status = "enviado"
            destinatario.motivo_falha = None  # limpa o aviso de tentativa adiada, se houve
            destinatario.enviado_em = datetime.now(UTC)
            if destinatario.decisor_id is not None:
                decisor = db.query(Decisor).filter_by(id=destinatario.decisor_id).one_or_none()
                if decisor is not None:
                    atividade_service.registrar(
                        db, tenant_id, conta_id=decisor.conta_id, tipo="sistema",
                        descricao=f"Campanha '{campanha.nome}' enviada",
                    )
            resultado["enviadas"] += 1
        elif adiado:
            # Canal de e-mail pausado por reputação (raio-X 2026-09-16) ou falha passageira de rede — não é falha do destinatário, fica
            # "pendente" pra tentar de novo no próximo ciclo.
            algum_adiado = True
            resultado["adiadas"] += 1
            if motivo_falha:  # falha de rede: os próximos também falhariam; para por aqui e retoma no ciclo seguinte
                logger.warning("CAMPANHA_ENVIO_INTERROMPIDO campanha=%s motivo=%s", campanha_id, motivo_falha)
                destinatario.motivo_falha = f"Envio adiado, nova tentativa automática em breve. {motivo_falha}"  # a tela mostra, em vez de "pendente" mudo
                interrompido = True
        else:
            destinatario.status = "falhou"
            destinatario.motivo_falha = motivo_falha
            resultado["falhas"] += 1
        campanha.processando_ate = _agora() + timedelta(minutes=_RESERVA_MINUTOS)  # renova a reserva a cada destinatário
        db.commit()
        if interrompido:
            break

    # Com algum adiado a campanha volta pro ciclo seguinte (fica "enviando", não "concluida") até o canal reabrir — senão
    # "concluida" com destinatários ainda "pendente" nunca mais seria reprocessada.
    db.refresh(campanha)
    if campanha.status in ("pronta", "enviando"):  # não sobrescreve um rascunho que o usuário acabou de abrir para editar
        if algum_adiado:
            campanha.status = "enviando"
        else:
            # Rodada só para os selecionados: quem ficou retido volta a pendente e a campanha ao rascunho, pronta para o próximo envio.
            liberados = (
                db.query(CampanhaDestinatario)
                .filter_by(campanha_id=campanha_id, tenant_id=tenant_id, status="retido")
                .update({"status": "pendente"}, synchronize_session=False)
            )
            campanha.status = "rascunho" if liberados else "concluida"
    campanha.processando_ate = None
    db.commit()


def _empresa_do_destinatario(db: Session, destinatario: CampanhaDestinatario) -> str | None:
    """Empresa do destinatário: a guardada na campanha (lista colada ou cópia do cadastro) e, nos antigos sem ela, o cadastro do contato de origem
    (nome fantasia, senão razão social)."""
    if destinatario.empresa:
        return destinatario.empresa
    if destinatario.decisor_id is None:
        return None
    conta = (
        db.query(Conta)
        .join(Decisor, Decisor.conta_id == Conta.id)
        .filter(Decisor.id == destinatario.decisor_id, Decisor.tenant_id == destinatario.tenant_id)
        .one_or_none()
    )
    return (conta.nome_fantasia or conta.nome) if conta is not None else None


def _personalizar(db: Session, texto: str | None, destinatario: CampanhaDestinatario) -> str:
    return campanha_personalizacao.renderizar(texto, destinatario.nome, _empresa_do_destinatario(db, destinatario))


def previa(db: Session, tenant_id: str, campanha_id: int, destinatario_id: int | None = None) -> dict:
    """Como o e-mail chega para um destinatário (o indicado ou o primeiro da lista), com os marcadores já trocados — sem o rodapé de descadastro."""
    campanha = obter(db, tenant_id, campanha_id)
    consulta = db.query(CampanhaDestinatario).filter_by(campanha_id=campanha.id, tenant_id=tenant_id)
    if destinatario_id is not None:
        consulta = consulta.filter_by(id=destinatario_id)
    destinatario = consulta.order_by(CampanhaDestinatario.id).first()
    if destinatario is None:
        return {
            "destinatario_nome": None,
            "assunto": campanha_personalizacao.renderizar(campanha.assunto, None, None),
            "corpo": campanha_personalizacao.renderizar(campanha.conteudo_email, None, None),
        }
    return {
        "destinatario_nome": destinatario.nome,
        "assunto": _personalizar(db, campanha.assunto, destinatario),
        "corpo": _personalizar(db, campanha.conteudo_email, destinatario),
    }


def _disparar_destinatario(
    db: Session,
    campanha: Campanha,
    destinatario: CampanhaDestinatario,
    email_provider: EmailProvider,
    whatsapp_provider: WhatsAppProvider,
) -> tuple[bool, str | None, bool]:
    """Retorna `(sucesso, motivo_falha, adiado)` — `adiado=True` quando o
    e-mail não foi tentado por o canal estar pausado por reputação
    (raio-X 2026-09-16: distinto de falha real, `processar_pendentes`
    deixa o destinatário `pendente` pra tentar de novo depois, em vez de
    `falhou`), mesmo raciocínio já aplicado em `envio_service.py`."""
    enviou_algum = False
    ultimo_motivo: str | None = None
    email_adiado = False
    falha_transitoria: str | None = None

    if "email" in campanha.canais and _email_valido(destinatario.email):  # endereço que não é e-mail nunca chega ao servidor
        if reputacao_service.canal_pausado(db, campanha.tenant_id, "email"):
            email_adiado = True
        else:
            corpo = f"{_personalizar(db, campanha.conteudo_email, destinatario)}\n\n{_link_optout(campanha.tenant_id, destinatario.id)}"
            resultado = email_provider.enviar(
                destinatario.email,
                _personalizar(db, campanha.assunto, destinatario),
                corpo,
                _REMETENTE_NOME,
                settings.sendgrid_remetente_email,
                campanha.tenant_id,
                pixel_url=rastreamento_service.url_pixel_campanha(campanha.tenant_id, destinatario.id),
                campanha_destinatario_id=destinatario.id,
            )
            if resultado.sucesso:
                enviou_algum = True
                destinatario.pixel_incluido = True
            elif resultado.transitoria:
                falha_transitoria = resultado.motivo_falha or "Falha temporária de rede ao enviar o e-mail."
            else:
                ultimo_motivo = resultado.motivo_falha

    if "whatsapp" in campanha.canais and destinatario.telefone and campanha.template_whatsapp_id:
        resultado = whatsapp_provider.enviar_template(destinatario.telefone, campanha.template_whatsapp_id, {})
        if resultado.sucesso:
            enviou_algum = True
        else:
            ultimo_motivo = resultado.motivo_falha

    adiado = (email_adiado or falha_transitoria is not None) and not enviou_algum and ultimo_motivo is None
    if adiado and falha_transitoria is not None:
        return False, falha_transitoria, True  # com motivo: o chamador interrompe o ciclo (a rede está fora), sem dar o destinatário por perdido
    if not enviou_algum and not adiado and ultimo_motivo is None:
        ultimo_motivo = "Destinatário sem e-mail/telefone compatível com os canais da campanha."
    return enviou_algum, ultimo_motivo, adiado


def _link_optout(tenant_id: str, destinatario_id: int) -> str:
    token = gerar_token_optout(tenant_id, destinatario_id)
    return f"Não quer mais receber esses e-mails? Descadastre-se: {settings.url_base_api}/opt-out/campanha/{token}"


def gerar_token_optout(tenant_id: str, destinatario_id: int) -> str:
    """Mesmo padrão stateless (HMAC) de `optout_service.gerar_token`,
    escopado a um destinatário de campanha em vez de um Decisor."""
    payload = f"{tenant_id}{_SEPARADOR}{destinatario_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def _validar_token_optout(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de opt-out inválido.")
    tenant_id, destinatario_id_str, assinatura = partes
    try:
        destinatario_id = int(destinatario_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de opt-out inválido.") from erro

    esperado = gerar_token_optout(tenant_id, destinatario_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de opt-out inválido.")
    return tenant_id, destinatario_id


def processar_optout_por_token(db: Session, token: str) -> dict:
    """Opt-out via link do e-mail da campanha — endpoint público. Quando o
    destinatário tem `decisor_id` (veio do CRM), propaga também para a
    supressão real (`optout_service.processar`), suprimindo cadências
    pro mesmo contato — destinatário avulso só fica suprimido aqui."""
    tenant_id, destinatario_id = _validar_token_optout(token)
    destinatario = db.query(CampanhaDestinatario).filter_by(id=destinatario_id, tenant_id=tenant_id).one_or_none()
    if destinatario is None:
        raise NaoEncontrado(f"Destinatário {destinatario_id} não encontrado")

    destinatario.status = "optout"
    if destinatario.decisor_id is not None:
        optout_service.processar(db, tenant_id, destinatario.decisor_id, origem="campanha")
    db.commit()
    return {"destinatario_id": destinatario.id, "suprimido": True}
