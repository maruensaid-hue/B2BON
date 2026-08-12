import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.graph.client import Neo4jClient, sincronizar_com_tolerancia
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.indicacao import Indicacao
from app.models.mensagem import Mensagem
from app.models.pesquisa_nps import PesquisaNps
from app.providers.rede_social.base import RedeSocialProvider
from app.services import aprovacao_service, auditoria_service, llm_helpers
from app.services.errors import NaoEncontrado, RegraNegocioViolada


def gerar_codigo(tenant_id: str, pesquisa_id: int) -> str:
    """Código de indicação rastreável, determinístico (HMAC) — mesmo
    mecanismo dos demais tokens do sistema (E11-H2)."""
    payload = f"{tenant_id}:{pesquisa_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:10]
    return f"IND-{pesquisa_id}-{assinatura}".upper()


def _canal_preferido(decisor: Decisor) -> str:
    if decisor.canal_provavel:
        return decisor.canal_provavel
    if decisor.telefone:
        return "whatsapp"
    return "email"


def solicitar(db: Session, tenant_id: str, pesquisa: PesquisaNps, llm: LLMProvider) -> Mensagem:
    """Pedido de indicação — só chamado para promotores (nota >= 9, E11-H2).

    A mensagem é submetida à mesma fila de aprovações do E4
    (`aprovacao_service.criar_proposta`, sem cadência associada) e sai
    imediatamente elegível ao dispatcher de envio assim que aprovada
    (`agendado_para` já setado para agora).
    """
    decisor = db.query(Decisor).filter_by(id=pesquisa.decisor_id).one()
    conta = db.query(Conta).filter_by(id=pesquisa.conta_id).one()
    canal = _canal_preferido(decisor)
    codigo = gerar_codigo(tenant_id, pesquisa.id)

    indicacao = Indicacao(
        tenant_id=tenant_id,
        promotor_decisor_id=decisor.id,
        promotor_conta_id=conta.id,
        codigo_indicacao=codigo,
        canal=canal,
        status="aguardando",
    )
    db.add(indicacao)
    db.flush()

    resposta = llm_helpers.gerar(
        llm,
        LLMRequest(
            prompt=(
                f"Escreva uma mensagem curta e calorosa para {decisor.nome}, da empresa {conta.nome}, que acabou "
                "de avaliar nossa parceria com nota máxima. Peça uma indicação de alguém que possa se beneficiar "
                f"da mesma solução, incluindo o código de indicação {codigo} para ele compartilhar."
            )
        )
    )

    mensagem = aprovacao_service.criar_proposta(
        db, tenant_id, None, decisor.id, canal, None, resposta.content, agendado_para=datetime.now(UTC)
    )

    auditoria_service.registrar(
        db,
        tenant_id,
        "indicacao_solicitada",
        "indicacao",
        indicacao.id,
        None,
        {"codigo_indicacao": codigo},
        conta_id=conta.id,
        canal=canal,
    )
    db.commit()
    return mensagem


def converter(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    codigo_indicacao: str,
    conta_id: int,
    rede_social: RedeSocialProvider,
    graph: Neo4jClient,
) -> Indicacao:
    """Liga a indicação a uma conta real gerada por ela (E11-H3).

    `Conta.origem = "indicacao"` é o gatilho que o painel do Flywheel
    (Onda 4, `panel_service.origem_oportunidade`) já sabe ler sem nenhuma
    mudança — foi desenhado prevendo esta onda.
    """
    indicacao = db.query(Indicacao).filter_by(tenant_id=tenant_id, codigo_indicacao=codigo_indicacao).one_or_none()
    if indicacao is None:
        raise NaoEncontrado(f"Indicação {codigo_indicacao} não encontrada")
    if indicacao.status == "convertida":
        raise RegraNegocioViolada("Indicação já convertida.")

    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")

    decisor = db.query(Decisor).filter_by(conta_id=conta.id).order_by(Decisor.id).first()
    identificador = (decisor.email or decisor.telefone) if decisor else None

    indicacao.status = "convertida"
    indicacao.conta_gerada_id = conta.id
    indicacao.indicado_nome = conta.nome
    indicacao.indicado_identificador = identificador
    indicacao.intra_rede = rede_social.eh_assinante(identificador) if identificador else False
    indicacao.convertida_em = datetime.now(UTC)

    conta.origem = "indicacao"

    sincronizar_com_tolerancia(
        lambda: graph.registrar_indicacao(tenant_id, indicacao.promotor_decisor_id, conta.id), "indicacao", indicacao.id
    )

    auditoria_service.registrar(
        db,
        tenant_id,
        "indicacao_convertida",
        "indicacao",
        indicacao.id,
        ator_id,
        {"conta_id": conta.id, "intra_rede": indicacao.intra_rede},
        conta_id=conta.id,
    )
    db.commit()
    db.refresh(indicacao)
    return indicacao


def listar(db: Session, tenant_id: str, status: str | None = None) -> list[Indicacao]:
    query = db.query(Indicacao).filter_by(tenant_id=tenant_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Indicacao.id).all()
