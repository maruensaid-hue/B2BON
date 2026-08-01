from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.registro_tratamento import (
    MinimizacaoResponseSchema,
    RegistroTratamentoCreateSchema,
    RegistroTratamentoSchema,
    RegistroTratamentoTenantSchema,
)
from app.services import ropa_service

router = APIRouter(prefix="/ropa", tags=["ropa"])


@router.get("", response_model=list[RegistroTratamentoSchema])
def listar_ropa_plataforma(db: Session = Depends(get_db)) -> list[RegistroTratamentoSchema]:
    return ropa_service.listar_ativos_plataforma(db)


@router.post("", response_model=RegistroTratamentoSchema, status_code=201)
def criar_versao_ropa_plataforma(
    dados: RegistroTratamentoCreateSchema,
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegistroTratamentoSchema:
    return ropa_service.criar_versao_plataforma(db, ator_id, dados)


@router.get("/tenant", response_model=RegistroTratamentoTenantSchema)
def ropa_tenant(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> RegistroTratamentoTenantSchema:
    return RegistroTratamentoTenantSchema(**ropa_service.gerar_ropa_tenant(db, tenant_id))


@router.get("/minimizacao", response_model=MinimizacaoResponseSchema)
def minimizacao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> MinimizacaoResponseSchema:
    return MinimizacaoResponseSchema(**ropa_service.verificar_minimizacao(db, tenant_id))
