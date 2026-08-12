from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services import campanha_service, optout_service

router = APIRouter(prefix="/opt-out", tags=["opt-out"])


@router.get("/email/{token}")
def optout_email(token: str, db: Session = Depends(get_db)) -> dict:
    """Link no e-mail (E9-H2) — endpoint público, o prospect não é usuário autenticado."""
    return optout_service.processar_por_token(db, token)


@router.get("/campanha/{token}")
def optout_campanha(token: str, db: Session = Depends(get_db)) -> dict:
    """Descadastro de campanha (e-mail de marketing/vendas) — endpoint
    público, mesmo padrão do opt-out de cadência acima."""
    return campanha_service.processar_optout_por_token(db, token)
