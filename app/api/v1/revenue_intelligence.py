"""Revenue Intelligence (Fase 16): métricas de receita do lado vendedor.

Gate: módulo CRM (as métricas são sobre o pipeline). O risco de renovação
de contratos públicos só entra para quem tem Bid Intelligence. Nada do
lado comprador (Public Procurement) aparece aqui.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import entitlements_do_usuario, get_db, get_plan_limits_provider, get_tenant_id, get_usuario_atual
from app.contexts.analytics import contract as analytics
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services.errors import ValidacaoFalhou
from app.models.usuario import Usuario

router = APIRouter(prefix="/inteligencia/receita", tags=["revenue-intelligence"])


@router.get("/metricas")
def metricas(
    inicio: datetime | None = None,
    fim: datetime | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
    db: Session = Depends(get_db),
) -> dict:
    if inicio and fim and inicio >= fim:
        raise ValidacaoFalhou("`inicio` deve ser anterior a `fim`.")
    com_licitacoes = entitlements_do_usuario(usuario, plan_limits).has_module("bids")
    return analytics.receita.metricas(db, tenant_id, inicio, fim, incluir_licitacoes=com_licitacoes)
