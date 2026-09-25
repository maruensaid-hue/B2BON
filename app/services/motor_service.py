from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.intelligence import contract as intel
from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest
from app.contexts.map import contract as map_contract
from app.models.interacao_tenant import InteracaoTenant
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services import auditoria_service, rede_social_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

_TIPOS_VALIDOS = map_contract.TIPOS_INTERACAO_VALIDOS


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
    return map_contract.classificar(score, settings.limiar_risco_critico_tenant, settings.limiar_risco_atencao_tenant)


def calcular_score_risco(db: Session, tenant_id: str) -> dict:
    """Score de risco de churn como função pura sobre os sinais registrados
    manualmente (metodologia — mesmo espírito do scoring S.H.A.R.K. do
    PREDATOR). Os limiares de classificação é que são configuráveis
    (Onda D)."""
    tenant = db.query(Tenant).filter_by(id=tenant_id).one_or_none()
    if tenant is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")

    interacoes = listar_interacoes(db, tenant_id)
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    fallback = licenca.data_inicio if licenca else tenant.criado_em
    resultado = map_contract.calcular_score(interacoes, fallback)
    score, dias_sem_contato, sinais = resultado["score"], resultado["dias_sem_contato"], resultado["sinais"]

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


def gerar_script_resgate(db: Session, tenant_id: str, llm: LLMProvider, tenant_id_operador: str | None = None) -> dict:
    """Script de reengajamento sugerido ao Admin B2B ON, gerado pela mesma
    camada `LLMProvider` já usada no PREDATOR (Onda D)."""
    risco = calcular_score_risco(db, tenant_id)
    perfil = rede_social_service.obter_perfil(db, tenant_id)
    interacoes = listar_interacoes(db, tenant_id)[:5]

    resumo_sinais = ", ".join(f"{tipo}: +{pontos}" for tipo, pontos in risco["sinais"].items()) or "nenhum sinal negativo recente"
    historico = "\n".join(f"- {i.tipo} ({i.criado_em:%Y-%m-%d}): {i.descricao or ''}" for i in interacoes) or "sem interações registradas"

    resposta = intel.gerar(
        db,
        llm,
        # Ferramenta interna CyberFort: o custo é de quem opera (tenant do
        # super_admin), nunca do tenant analisado.
        intel.ContextoIA(tenant_id=tenant_id_operador or tenant_id, feature="map.script_resgate_tenant", workflow=f"tenant_analisado:{tenant_id}"),
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
