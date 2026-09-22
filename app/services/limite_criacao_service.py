from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.cadencia import Cadencia
from app.models.campanha import Campanha
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services.errors import RegraNegocioViolada


def _inicio_do_mes_atual() -> datetime:
    """UTC, mesmo padrão de `franquia_service`/`crm_service` — evita
    misturar fuso local do processo com timestamps gravados em UTC pelo
    banco (raio-X 2026-09-21, bug real do dashboard de atividade)."""
    agora = datetime.now(UTC)
    return agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def verificar_limite_cadencias(db: Session, tenant_id: str, plan_limits: PlanLimitsProvider) -> None:
    """Chamada na criação de uma nova Cadência — bloqueia quando o tenant já
    criou, neste mês corrente, o número de cadências permitido pelo plano
    da licença ativa. `None` = sem teto (mesma semântica dos limites de
    enriquecimento em `enriquecimento_limite_service`)."""
    limite = plan_limits.obter_limite_cadencias_mes(tenant_id)
    if limite is None:
        return
    usado = (
        db.query(Cadencia)
        .filter(Cadencia.tenant_id == tenant_id, Cadencia.criado_em >= _inicio_do_mes_atual())
        .count()
    )
    if usado >= limite:
        raise RegraNegocioViolada(
            f"Limite de cadências do seu plano atingido neste mês ({limite}). "
            "Volta a funcionar no próximo mês, ou fale com o administrador pra fazer upgrade do seu plano."
        )


def verificar_limite_campanhas(db: Session, tenant_id: str, plan_limits: PlanLimitsProvider) -> None:
    limite = plan_limits.obter_limite_campanhas_mes(tenant_id)
    if limite is None:
        return
    usado = (
        db.query(Campanha)
        .filter(Campanha.tenant_id == tenant_id, Campanha.criado_em >= _inicio_do_mes_atual())
        .count()
    )
    if usado >= limite:
        raise RegraNegocioViolada(
            f"Limite de campanhas do seu plano atingido neste mês ({limite}). "
            "Volta a funcionar no próximo mês, ou fale com o administrador pra fazer upgrade do seu plano."
        )
