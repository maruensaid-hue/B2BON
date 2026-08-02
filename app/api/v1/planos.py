from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.plano import PlanoSchema
from app.services import tenant_service

router = APIRouter(prefix="/planos", tags=["planos"])


@router.get("", response_model=list[PlanoSchema])
def listar_planos(db: Session = Depends(get_db)) -> list[PlanoSchema]:
    """Lista pública dos planos — não exige autenticação (Onda A)."""
    return tenant_service.listar_planos(db)
