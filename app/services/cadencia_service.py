from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.models.oferta import Oferta
from app.models.toque_cadencia import ToqueCadencia
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.cadencia import CadenciaCreateSchema
from app.services import aprovacao_service, auditoria_service, comunicacao_service, franquia_service, optout_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

MINIMO_TOQUES = 5
MINIMO_CANAIS_DISTINTOS = 2


def obter(db: Session, tenant_id: str, cadencia_id: int) -> Cadencia:
    cadencia = db.query(Cadencia).filter_by(id=cadencia_id, tenant_id=tenant_id).one_or_none()
    if cadencia is None:
        raise NaoEncontrado(f"Cadência {cadencia_id} não encontrada")
    return cadencia


def listar(db: Session, tenant_id: str) -> list[Cadencia]:
    return db.query(Cadencia).filter_by(tenant_id=tenant_id).order_by(Cadencia.id.desc()).all()


def toques_da_cadencia(db: Session, cadencia_id: int) -> list[ToqueCadencia]:
    return db.query(ToqueCadencia).filter_by(cadencia_id=cadencia_id).order_by(ToqueCadencia.ordem).all()


def criar(db: Session, tenant_id: str, ator_id: str | None, dados: CadenciaCreateSchema) -> Cadencia:
    """Cadência com no mínimo 5 toques distribuídos entre canais disponíveis (E3-H1)."""
    if len(dados.toques) < MINIMO_TOQUES:
        raise RegraNegocioViolada(f"Uma cadência precisa de no mínimo {MINIMO_TOQUES} toques.")

    canais = {toque.canal for toque in dados.toques}
    if len(canais) < MINIMO_CANAIS_DISTINTOS:
        raise RegraNegocioViolada("Os toques precisam estar distribuídos entre pelo menos 2 canais.")

    cadencia = Cadencia(
        tenant_id=tenant_id, nome=dados.nome, canais=sorted(canais), status="rascunho", tipo=dados.tipo
    )
    db.add(cadencia)
    db.flush()

    for toque in dados.toques:
        db.add(
            ToqueCadencia(
                tenant_id=tenant_id,
                cadencia_id=cadencia.id,
                ordem=toque.ordem,
                canal=toque.canal,
                intervalo_dias_apos_anterior=toque.intervalo_dias_apos_anterior,
                template_whatsapp_id=toque.template_whatsapp_id,
                ab_teste_habilitado=toque.ab_teste_habilitado,
            )
        )

    auditoria_service.registrar(
        db, tenant_id, "cadencia_criada", "cadencia", cadencia.id, ator_id, {"toques": len(dados.toques)}
    )
    db.commit()
    db.refresh(cadencia)
    return cadencia


def _contexto_de_geracao(db: Session, tenant_id: str) -> tuple[ICP, Oferta, ConfiguracaoComunicacao]:
    icp = db.query(ICP).filter_by(tenant_id=tenant_id, ativo=True).first()
    if icp is None:
        raise RegraNegocioViolada("Sem ICP ativo, o motor não inicia prospecção.")
    oferta = db.query(Oferta).filter_by(tenant_id=tenant_id, ativo=True).first()
    if oferta is None:
        raise RegraNegocioViolada("Cadastre ao menos uma oferta antes de gerar uma cadência.")
    config = db.query(ConfiguracaoComunicacao).filter_by(tenant_id=tenant_id).one_or_none()
    if config is None:
        raise RegraNegocioViolada("Configure tom e restrições de comunicação antes de gerar uma cadência.")
    return icp, oferta, config


_ENQUADRAMENTO_VARIANTE = {
    "A": "Use um tom direto e objetivo, indo reto ao ponto.",
    "B": "Use um tom consultivo, abrindo com uma pergunta sobre o contexto do decisor.",
}


def variante_ab_para_decisor(decisor_id: int) -> str:
    """Distribuição controlada e reproduzível (não aleatória) entre as duas
    variantes do teste A/B (E3-H5)."""
    return "A" if decisor_id % 2 == 0 else "B"


def _gerar_conteudo_toque(
    llm: LLMProvider,
    icp: ICP,
    oferta: Oferta,
    config: ConfiguracaoComunicacao,
    conta: Conta,
    decisor: Decisor,
    toque: ToqueCadencia,
    variante: str | None = None,
) -> str | None:
    """Mensagem personalizada por conta/decisor — não mala direta (E3-H1).

    Retorna None se o texto gerado violar as restrições do E1-H3 (melhor
    esforço: o toque é pulado, não bloqueia o restante do lote).
    """
    enquadramento_variante = f" {_ENQUADRAMENTO_VARIANTE[variante]}" if variante else ""
    resposta = llm.generate(
        LLMRequest(
            prompt=(
                f"Escreva o toque {toque.ordem} (canal {toque.canal}) de uma cadência de prospecção "
                f"para {decisor.nome} ({decisor.cargo or 'decisor'}) na empresa {conta.nome}, "
                f"aderente ao ICP '{icp.nome}' (segmento {icp.segmento}), oferecendo '{oferta.nome}'. "
                f"Tom: {config.tom}.{enquadramento_variante} Nunca mencione: "
                f"{', '.join(config.restricoes) if config.restricoes else 'nenhuma restrição'}."
            )
        )
    )
    if comunicacao_service.validar_texto(resposta.content, config.restricoes):
        return None
    return resposta.content


def _rodape_por_canal(db: Session, tenant_id: str, decisor: Decisor, canal: str, conteudo: str) -> str:
    if canal == "email":
        token = optout_service.gerar_token(tenant_id, decisor.id)
        return f"{conteudo}\n\nPara não receber mais e-mails: /api/v1/opt-out/email/{token}"
    if canal == "whatsapp":
        return f"{conteudo}\n\nResponda SAIR para parar de receber mensagens."
    return conteudo


def gerar_para_lote(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    cadencia_id: int,
    conta_ids: list[int],
    llm: LLMProvider,
) -> dict:
    """Gera os toques personalizados para um lote de contas e os submete à
    fila de aprovações — cadência inteira antes de ativar (E3-H1)."""
    cadencia = obter(db, tenant_id, cadencia_id)
    toques = toques_da_cadencia(db, cadencia.id)
    icp, oferta, config = _contexto_de_geracao(db, tenant_id)

    contas_processadas: list[int] = []
    contas_sem_decisor: list[int] = []
    mensagens_geradas = 0

    for conta_id in conta_ids:
        conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
        if conta is None:
            raise NaoEncontrado(f"Conta {conta_id} não encontrada")

        decisor = db.query(Decisor).filter_by(conta_id=conta.id).order_by(Decisor.id).first()
        if decisor is None:
            contas_sem_decisor.append(conta_id)
            continue

        contas_processadas.append(conta_id)
        for toque in toques:
            variante = variante_ab_para_decisor(decisor.id) if toque.ab_teste_habilitado else None
            conteudo = _gerar_conteudo_toque(llm, icp, oferta, config, conta, decisor, toque, variante)
            if conteudo is None:
                continue
            conteudo = _rodape_por_canal(db, tenant_id, decisor, toque.canal, conteudo)
            aprovacao_service.criar_proposta(
                db,
                tenant_id,
                cadencia.id,
                decisor.id,
                toque.canal,
                toque.template_whatsapp_id,
                conteudo,
                toque_cadencia_id=toque.id,
                variante_ab=variante,
            )
            mensagens_geradas += 1

    if mensagens_geradas > 0:
        cadencia.status = "aguardando_aprovacao"

    auditoria_service.registrar(
        db,
        tenant_id,
        "cadencia_gerada_para_lote",
        "cadencia",
        cadencia.id,
        ator_id,
        {"contas_processadas": contas_processadas, "mensagens_geradas": mensagens_geradas},
    )
    db.commit()

    return {
        "contas_processadas": contas_processadas,
        "contas_sem_decisor": contas_sem_decisor,
        "mensagens_geradas": mensagens_geradas,
    }


def ativar(
    db: Session, tenant_id: str, ator_id: str | None, cadencia_id: int, plan_limits: PlanLimitsProvider
) -> dict:
    """Ativa a cadência: exige todos os toques aprovados, calcula o
    agendamento e consome a franquia das contas envolvidas (E3-H1, gancho
    da Onda 1 em `franquia_service.consumir_para_ativacao`)."""
    cadencia = obter(db, tenant_id, cadencia_id)

    mensagens = db.query(Mensagem).filter_by(tenant_id=tenant_id, cadencia_id=cadencia.id).all()
    if not mensagens:
        raise RegraNegocioViolada("Cadência não tem toques gerados para nenhuma conta.")

    for mensagem in mensagens:
        aprovacao = (
            db.query(Aprovacao)
            .filter_by(mensagem_id=mensagem.id)
            .order_by(Aprovacao.id.desc())
            .first()
        )
        if aprovacao is None or aprovacao.status != "aprovado":
            raise RegraNegocioViolada(
                "Cadência tem toques pendentes de aprovação — não pode ser ativada."
            )

    agora = datetime.now(UTC)
    mensagens_por_decisor: dict[int, list[Mensagem]] = {}
    for mensagem in mensagens:
        mensagens_por_decisor.setdefault(mensagem.decisor_id, []).append(mensagem)

    toques_por_id = {toque.id: toque for toque in toques_da_cadencia(db, cadencia.id)}
    conta_ids: set[int] = set()

    for decisor_id, mensagens_do_decisor in mensagens_por_decisor.items():
        decisor = db.query(Decisor).filter_by(id=decisor_id).one()
        conta_ids.add(decisor.conta_id)

        mensagens_ordenadas = sorted(
            mensagens_do_decisor, key=lambda m: toques_por_id[m.toque_cadencia_id].ordem if m.toque_cadencia_id else 0
        )
        data_acumulada = agora
        for mensagem in mensagens_ordenadas:
            toque = toques_por_id.get(mensagem.toque_cadencia_id)
            if toque and toque.ordem > 1:
                data_acumulada = data_acumulada + timedelta(days=toque.intervalo_dias_apos_anterior)
            mensagem.agendado_para = data_acumulada

    franquia = franquia_service.consumir_para_ativacao(db, tenant_id, ator_id, sorted(conta_ids), plan_limits)

    cadencia.status = "ativa"
    cadencia.data_inicio = agora
    auditoria_service.registrar(
        db, tenant_id, "cadencia_ativada", "cadencia", cadencia.id, ator_id, {"contas": sorted(conta_ids)}
    )
    db.commit()
    db.refresh(cadencia)

    return {"cadencia": cadencia, "franquia": franquia}
