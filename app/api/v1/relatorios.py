from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_plan_limits_provider, get_usuario_atual, permitir_gestao_hierarquica
from app.models.usuario import Usuario
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.relatorio import (
    ConfiguracaoRelatorioSchema,
    DashboardRelatorioSchema,
    DefinirConfiguracaoRelatorioRequestSchema,
)
from app.services import relatorio_service
from app.services.errors import NaoEncontrado

router = APIRouter(prefix="/relatorios", tags=["relatorios"], dependencies=[Depends(permitir_gestao_hierarquica)])


@router.get("/dashboard", response_model=DashboardRelatorioSchema)
def dashboard(
    periodo_dias: int = 7,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> DashboardRelatorioSchema:
    """Volumetria/franquia/inadimplência/receita/churn (Fase 3 da
    hierarquia, raio-X) — escopo automático por papel: super_admin vê
    tudo, admin de distribuidor/revendedor vê a própria subárvore."""
    return relatorio_service.dashboard(db, usuario, periodo_dias, plan_limits)


@router.get("/configuracao", response_model=ConfiguracaoRelatorioSchema)
def obter_configuracao(db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)) -> ConfiguracaoRelatorioSchema:
    config = relatorio_service.obter_configuracao(db, usuario.tenant_id)
    if config is None:
        raise NaoEncontrado("Nenhuma cadência de relatório configurada.")
    return config


@router.put("/configuracao", response_model=ConfiguracaoRelatorioSchema)
def definir_configuracao(
    dados: DefinirConfiguracaoRelatorioRequestSchema,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
) -> ConfiguracaoRelatorioSchema:
    return relatorio_service.definir_configuracao(db, usuario.tenant_id, dados.cadencia)
