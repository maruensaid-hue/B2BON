from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db
from app.schemas.representante import (
    AtualizarRepresentanteRequestSchema,
    BaseLiquidaComissaoSchema,
    CriarRepresentanteRequestSchema,
    RepresentanteSchema,
    RepresentanteSelfServiceSchema,
)
from app.services import comissao_service, representante_service

router = APIRouter(prefix="/representantes", tags=["representantes"])


@router.get("/self-service", response_model=list[RepresentanteSelfServiceSchema])
def listar_self_service(db: Session = Depends(get_db)) -> list[RepresentanteSelfServiceSchema]:
    """Pública — alimenta o `<select>` obrigatório de `CriarConta.tsx`.
    Só id+nome dos representantes ativos, nunca CPF/PIX."""
    return representante_service.listar_self_service(db)


@router.get("/base-liquida-comissao", dependencies=[Depends(exigir_papel("super_admin"))])
def base_liquida(db: Session = Depends(get_db)) -> dict:
    """D-073: alíquotas de impostos e infraestrutura descontadas antes da comissão (todas as vendas)."""
    aliquotas = comissao_service.aliquotas(db)
    db.commit()
    return aliquotas


@router.put("/base-liquida-comissao", dependencies=[Depends(exigir_papel("super_admin"))])
def definir_base_liquida(dados: BaseLiquidaComissaoSchema, ator_id: str | None = Depends(get_ator_id),
                         db: Session = Depends(get_db)) -> dict:
    return comissao_service.definir(db, dados.impostos, dados.infraestrutura, dados.motivo, ator_id)


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
