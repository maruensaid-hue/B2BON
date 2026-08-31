from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enriquecimento_semanal_consumo import EnriquecimentoSemanalConsumo
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services.errors import RegraNegocioViolada

_ROTULOS = {"site": "de site", "contatos": "de contatos"}


def _semana_atual() -> str:
    return datetime.now(UTC).strftime("%G-W%V")


def _usado_na_semana(db: Session, tenant_id: str, tipo: str, semana: str) -> int:
    return (
        db.query(EnriquecimentoSemanalConsumo)
        .filter_by(tenant_id=tenant_id, tipo=tipo, semana=semana)
        .count()
    )


def _obter_limite(plan_limits: PlanLimitsProvider, tenant_id: str, tipo: str) -> int | None:
    if tipo == "site":
        return plan_limits.obter_limite_enriquecimento_site_semanal(tenant_id)
    return plan_limits.obter_limite_enriquecimento_contatos_semanal(tenant_id)


def verificar_e_registrar(db: Session, tenant_id: str, tipo: str, plan_limits: PlanLimitsProvider) -> None:
    """Chamada no início de `conta_service.enriquecer` (tipo="site") e
    `conta_service.mapear_decisores` (tipo="contatos") — raio-X
    2026-08-28: todo plano tem limite semanal, proporcional à franquia
    mensal; `None` (reservado, nenhum plano hoje) libera sem checar nada."""
    limite = _obter_limite(plan_limits, tenant_id, tipo)
    if limite is None:
        return

    semana = _semana_atual()
    usado = _usado_na_semana(db, tenant_id, tipo, semana)
    if usado >= limite:
        raise RegraNegocioViolada(
            f"Limite semanal de pesquisas {_ROTULOS[tipo]} atingido ({limite}/semana). "
            "Volta a funcionar na semana que vem, ou fale com o administrador pra fazer upgrade do seu plano."
        )

    db.add(EnriquecimentoSemanalConsumo(tenant_id=tenant_id, tipo=tipo, semana=semana))
    db.commit()


def _contador(db: Session, tenant_id: str, tipo: str, plan_limits: PlanLimitsProvider) -> dict:
    limite = _obter_limite(plan_limits, tenant_id, tipo)
    if limite is None:
        return {"limite": None, "usado": 0, "restante": None}
    usado = _usado_na_semana(db, tenant_id, tipo, _semana_atual())
    return {"limite": limite, "usado": usado, "restante": max(limite - usado, 0)}


def obter_limites(db: Session, tenant_id: str, plan_limits: PlanLimitsProvider) -> dict:
    return {
        "site": _contador(db, tenant_id, "site", plan_limits),
        "contatos": _contador(db, tenant_id, "contatos", plan_limits),
    }
