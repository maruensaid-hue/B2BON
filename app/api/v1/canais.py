from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.rampa import RampaStatusSchema
from app.services import rampa_service

router = APIRouter(prefix="/canais", tags=["canais"])


@router.get("/{canal}/rampa", response_model=RampaStatusSchema)
def rampa_do_canal(
    canal: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> RampaStatusSchema:
    """Contador visível da rampa de aquecimento (E10-H1)."""
    return RampaStatusSchema(**rampa_service.status_rampa(db, tenant_id, canal))
