from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.plano import PlanoSchema
from app.services import tenant_service

router = APIRouter(prefix="/planos", tags=["planos"])


@router.get("", response_model=list[PlanoSchema])
def listar_planos(apenas_self_service: bool = False, db: Session = Depends(get_db)) -> list[PlanoSchema]:
    """Lista pública dos planos — não exige autenticação (Onda A).
    `apenas_self_service=True` (usado pela tela de cadastro público)
    esconde planos como "Teste", só concedíveis por convite gratuito."""
    return tenant_service.listar_planos(db, apenas_self_service)
