from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.rampa import RampaStatusSchema
from app.schemas.reputacao import SaudeCanalSchema
from app.services import rampa_service, reputacao_service

router = APIRouter(prefix="/canais", tags=["canais"])


@router.get("/{canal}/rampa", response_model=RampaStatusSchema)
def rampa_do_canal(
    canal: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> RampaStatusSchema:
    """Contador visível da rampa de aquecimento (E10-H1)."""
    return RampaStatusSchema(**rampa_service.status_rampa(db, tenant_id, canal))


@router.get("/{canal}/saude", response_model=SaudeCanalSchema)
def saude_do_canal(
    canal: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> SaudeCanalSchema:
    """Painel de saúde por canal com limiares de alerta (E10-H2)."""
    return SaudeCanalSchema(**reputacao_service.status_saude(db, tenant_id, canal))


@router.post("/{canal}/reativar", response_model=SaudeCanalSchema)
def reativar_canal(
    canal: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SaudeCanalSchema:
    """Reativação manual do canal pausado automaticamente (E10-H2)."""
    return SaudeCanalSchema(**reputacao_service.reativar(db, tenant_id, ator_id, canal))
