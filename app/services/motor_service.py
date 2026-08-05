from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.models.interacao_tenant import InteracaoTenant
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services import auditoria_service, llm_helpers, rede_social_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

_TIPOS_VALIDOS = {
    "contato",
    "ticket_suporte",
    "reclamacao",
    "feedback_positivo",
    "reuniao_remarcada",
    "mencionou_concorrente",
}
_TIPOS_CONTATO = {"contato", "feedback_positivo"}
_JANELA_SINAIS_DIAS = 30


def registrar_interacao(
    db: Session, tenant_id: str, ator_id: str | None, tipo: str, descricao: str | None = None
) -> InteracaoTenant:
    if tipo not in _TIPOS_VALIDOS:
        raise ValidacaoFalhou(f"Tipo de interação inválido: {tipo}")
    if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")

    interacao = InteracaoTenant(
        tenant_id=tenant_id,
        tipo=tipo,
        descricao=descricao,
        criado_por_usuario_id=int(ator_id) if ator_id else None,
    )
    db.add(interacao)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "interacao_tenant_registrada", "interacao_tenant", interacao.id, ator_id, {"tipo": tipo}
    )
    db.commit()
    db.refresh(interacao)
    return interacao


def listar_interacoes(db: Session, tenant_id: str) -> list[InteracaoTenant]:
    return (
        db.query(InteracaoTenant)
        .filter_by(tenant_id=tenant_id)
        .order_by(InteracaoTenant.criado_em.desc())
        .all()
    )


def _classificar(score: float) -> str:
    if score >= settings.limiar_risco_critico_tenant:
        return "critico"
    if score >= settings.limiar_risco_atencao_tenant:
        return "atencao"
    return "saudavel"


def calcular_score_risco(db: Session, tenant_id: str) -> dict:
    """Score de risco de churn como função pura sobre os sinais registrados
    manualmente (metodologia — mesmo espírito do scoring S.H.A.R.K. do
    PREDATOR). Os limiares de classificação é que são configuráveis
    (Onda D)."""
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")

    interacoes = listar_interacoes(db, tenant_id)
    agora = datetime.now(UTC)

    ultimo_contato_em = next(
        (i.criado_em for i in interacoes if i.tipo in _TIPOS_CONTATO), None
    )
    if ultimo_contato_em is None:
        licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
        ultimo_contato_em = licenca.data_inicio if licenca else tenant.criado_em

    dias_sem_contato = (agora - ultimo_contato_em.replace(tzinfo=UTC)).days

    score = 10.0
    sinais: dict[str, int] = {}

    if dias_sem_contato > 30:
        score += 30
        sinais["dias_sem_contato"] = 30
    elif dias_sem_contato > 14:
        score += 20
        sinais["dias_sem_contato"] = 20
    elif dias_sem_contato > 7:
        score += 10
        sinais["dias_sem_contato"] = 10

    corte = agora - timedelta(days=_JANELA_SINAIS_DIAS)

    reclamacoes_recentes = sum(
        1 for i in interacoes if i.tipo == "reclamacao" and i.criado_em.replace(tzinfo=UTC) >= corte
    )
    if reclamacoes_recentes:
        pontos = min(reclamacoes_recentes * 15, 45)
        score += pontos
        sinais["reclamacoes"] = pontos

    if any(i.tipo == "mencionou_concorrente" and i.criado_em.replace(tzinfo=UTC) >= corte for i in interacoes):
        score += 20
        sinais["mencionou_concorrente"] = 20

    if any(i.tipo == "reuniao_remarcada" and i.criado_em.replace(tzinfo=UTC) >= corte for i in interacoes):
        score += 15
        sinais["reuniao_remarcada"] = 15

    if any(i.tipo == "feedback_positivo" and i.criado_em.replace(tzinfo=UTC) >= corte for i in interacoes):
        score -= 20
        sinais["feedback_positivo"] = -20

    score = max(0.0, min(100.0, score))

    return {
        "tenant_id": tenant_id,
        "score": score,
        "classificacao": _classificar(score),
        "dias_sem_contato": dias_sem_contato,
        "sinais": sinais,
    }


def ranking_saude_tenants(db: Session) -> list[dict]:
    """Cross-tenant, só para o Admin B2B ON (super_admin) — mesmo padrão de
    `panel_service.ranking_assinantes` (E8-H3 do PREDATOR), agora sobre a
    tabela `Tenant` real (Onda A)."""
    agora = datetime.now(UTC)
    resultado = []
    for tenant in db.query(Tenant).all():
        risco = calcular_score_risco(db, tenant.id)
        perfil = rede_social_service.obter_perfil(db, tenant.id)
        licenca = db.query(Licenca).filter_by(tenant_id=tenant.id).one_or_none()
        plano = db.query(Plano).filter_by(id=licenca.plano_id).one_or_none() if licenca else None

        valor_mensal = plano.preco_mensal if plano else 0.0
        meses_como_cliente = (
            max((agora - licenca.data_inicio.replace(tzinfo=UTC)).days / 30, 0.0) if licenca else 0.0
        )
        valor_em_risco = valor_mensal * meses_como_cliente if risco["classificacao"] != "saudavel" else 0.0

        resultado.append(
            {
                "tenant_id": tenant.id,
                "nome_exibicao": perfil.nome_exibicao,
                "score": risco["score"],
                "classificacao": risco["classificacao"],
                "meses_como_cliente": meses_como_cliente,
                "valor_mensal": valor_mensal,
                "valor_em_risco": valor_em_risco,
            }
        )
    resultado.sort(key=lambda item: item["score"], reverse=True)
    return resultado


def dashboard_motor(db: Session) -> dict:
    ranking = ranking_saude_tenants(db)
    total = len(ranking)
    return {
        "score_medio": (sum(item["score"] for item in ranking) / total) if total else None,
        "total_tenants": total,
        "criticos": sum(1 for item in ranking if item["classificacao"] == "critico"),
        "atencao": sum(1 for item in ranking if item["classificacao"] == "atencao"),
        "saudaveis": sum(1 for item in ranking if item["classificacao"] == "saudavel"),
        "valor_total_em_risco": sum(item["valor_em_risco"] for item in ranking),
    }


def gerar_script_resgate(db: Session, tenant_id: str, llm: LLMProvider) -> dict:
    """Script de reengajamento sugerido ao Admin B2B ON, gerado pela mesma
    camada `LLMProvider` já usada no PREDATOR (Onda D)."""
    risco = calcular_score_risco(db, tenant_id)
    perfil = rede_social_service.obter_perfil(db, tenant_id)
    interacoes = listar_interacoes(db, tenant_id)[:5]

    resumo_sinais = ", ".join(f"{tipo}: +{pontos}" for tipo, pontos in risco["sinais"].items()) or "nenhum sinal negativo recente"
    historico = "\n".join(f"- {i.tipo} ({i.criado_em:%Y-%m-%d}): {i.descricao or ''}" for i in interacoes) or "sem interações registradas"

    resposta = llm_helpers.gerar(
        llm,
        LLMRequest(
            prompt=(
                f"O tenant '{perfil.nome_exibicao}' da B2B ON está classificado como "
                f"'{risco['classificacao']}' (score de risco de churn {risco['score']}/100). "
                f"Sinais que elevaram o score: {resumo_sinais}. "
                f"Dias sem contato: {risco['dias_sem_contato']}. "
                f"Últimas interações registradas:\n{historico}\n\n"
                "Escreva uma mensagem curta e direta que o Admin da B2B ON possa enviar a este "
                "cliente para reengajar e reduzir o risco de cancelamento."
            ),
            system="Você ajuda um Customer Success B2B a redigir mensagens de resgate de clientes em risco de churn.",
        )
    )

    return {
        "tenant_id": tenant_id,
        "script": resposta.content,
        "justificativa": f"Classificação '{risco['classificacao']}' com sinais: {resumo_sinais}.",
    }
