from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.busca import ResultadoBuscaSchema
from app.services import busca_service

router = APIRouter(prefix="/busca", tags=["busca"])


@router.get("", response_model=list[ResultadoBuscaSchema])
def buscar(
    q: str = "",
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ResultadoBuscaSchema]:
    return busca_service.buscar(db, usuario, q)
