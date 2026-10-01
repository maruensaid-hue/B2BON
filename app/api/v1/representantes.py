from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db
from app.schemas.representante import (
    AtualizarRepresentanteRequestSchema,
    CriarRepresentanteRequestSchema,
    RepresentanteSchema,
    RepresentanteSelfServiceSchema,
)
from app.services import representante_service

router = APIRouter(prefix="/representantes", tags=["representantes"])


@router.get("/self-service", response_model=list[RepresentanteSelfServiceSchema])
def listar_self_service(db: Session = Depends(get_db)) -> list[RepresentanteSelfServiceSchema]:
    """Pública — alimenta o `<select>` obrigatório de `CriarConta.tsx`.
    Só id+nome dos representantes ativos, nunca CPF/PIX."""
    return representante_service.listar_self_service(db)


@router.get("", response_model=list[RepresentanteSchema], dependencies=[Depends(exigir_papel("super_admin"))])
def listar(db: Session = Depends(get_db)) -> list[RepresentanteSchema]:
    return representante_service.listar(db)


@router.post(
    "", response_model=RepresentanteSchema, status_code=201, dependencies=[Depends(exigir_papel("super_admin"))]
)
def criar(dados: CriarRepresentanteRequestSchema, db: Session = Depends(get_db)) -> RepresentanteSchema:
    return representante_service.criar(db, dados.model_dump())


@router.put(
    "/{representante_id}", response_model=RepresentanteSchema, dependencies=[Depends(exigir_papel("super_admin"))]
)
def atualizar(
    representante_id: int, dados: AtualizarRepresentanteRequestSchema, db: Session = Depends(get_db)
) -> RepresentanteSchema:
    return representante_service.atualizar(db, representante_id, dados.model_dump())
