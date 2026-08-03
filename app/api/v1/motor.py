from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_llm_provider
from app.llm.base import LLMProvider
from app.schemas.motor import (
    DashboardMotorSchema,
    InteracaoTenantSchema,
    RegistrarInteracaoRequestSchema,
    SaudeTenantSchema,
    ScoreRiscoSchema,
    ScriptResgateSchema,
)
from app.services import motor_service

router = APIRouter(prefix="/motor", tags=["motor"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.post("/interacoes", response_model=InteracaoTenantSchema, status_code=201)
def registrar_interacao(
    dados: RegistrarInteracaoRequestSchema,
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> InteracaoTenantSchema:
    return motor_service.registrar_interacao(db, dados.tenant_id, ator_id, dados.tipo, dados.descricao)


@router.get("/tenants/{tenant_id}/interacoes", response_model=list[InteracaoTenantSchema])
def listar_interacoes(tenant_id: str, db: Session = Depends(get_db)) -> list[InteracaoTenantSchema]:
    return motor_service.listar_interacoes(db, tenant_id)


@router.get("/saude-tenants", response_model=list[SaudeTenantSchema])
def saude_tenants(db: Session = Depends(get_db)) -> list[SaudeTenantSchema]:
    return motor_service.ranking_saude_tenants(db)


@router.get("/tenants/{tenant_id}/score-risco", response_model=ScoreRiscoSchema)
def score_risco(tenant_id: str, db: Session = Depends(get_db)) -> ScoreRiscoSchema:
    return motor_service.calcular_score_risco(db, tenant_id)


@router.get("/dashboard", response_model=DashboardMotorSchema)
def dashboard(db: Session = Depends(get_db)) -> DashboardMotorSchema:
    return motor_service.dashboard_motor(db)


@router.get("/tenants/{tenant_id}/script-resgate", response_model=ScriptResgateSchema)
def script_resgate(
    tenant_id: str,
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ScriptResgateSchema:
    return motor_service.gerar_script_resgate(db, tenant_id, llm)
