from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db
from app.schemas.plano import AtualizarPlanoRequestSchema, CriarPlanoRequestSchema, PlanoSchema
from app.services import tenant_service

router = APIRouter(prefix="/planos", tags=["planos"])


@router.get("", response_model=list[PlanoSchema])
def listar_planos(apenas_self_service: bool = False, db: Session = Depends(get_db)) -> list[PlanoSchema]:
    """Lista pública dos planos — não exige autenticação (Onda A).
    `apenas_self_service=True` (usado pela tela de cadastro público)
    esconde planos como "Teste", só concedíveis por convite gratuito."""
    return tenant_service.listar_planos(db, apenas_self_service)


@router.post("", response_model=PlanoSchema, status_code=201, dependencies=[Depends(exigir_papel("super_admin"))])
def criar_plano(dados: CriarPlanoRequestSchema, db: Session = Depends(get_db)) -> PlanoSchema:
    return tenant_service.criar_plano(db, dados.model_dump())


@router.put("/{plano_id}", response_model=PlanoSchema, dependencies=[Depends(exigir_papel("super_admin"))])
def atualizar_plano(plano_id: int, dados: AtualizarPlanoRequestSchema, db: Session = Depends(get_db)) -> PlanoSchema:
    return tenant_service.atualizar_plano(db, plano_id, dados.model_dump())
