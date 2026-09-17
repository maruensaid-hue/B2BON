from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.inteligencia_rede import FitIcpRedeSchema
from app.services import sinal_oportunidade_service

router = APIRouter(prefix="/inteligencia-rede", tags=["inteligencia-rede"])


@router.get("/fit-icp", response_model=list[FitIcpRedeSchema])
def listar_fit_icp_rede(
    icp_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[FitIcpRedeSchema]:
    """ICP Agent — fit ICP×Rede (master prompt §25, §60, Fase 3B)."""
    return sinal_oportunidade_service.listar_fit_icp_rede(db, tenant_id, icp_id)
