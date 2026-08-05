from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.oferta import MaterialOfertaSchema, OfertaCreateSchema, OfertaSchema
from app.services import oferta_service

router = APIRouter(prefix="/ofertas", tags=["ofertas"])


@router.post("", response_model=OfertaSchema, status_code=201)
def criar_oferta(
    dados: OfertaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> OfertaSchema:
    return oferta_service.criar(db, tenant_id, ator_id, dados)


@router.get("", response_model=list[OfertaSchema])
def listar_ofertas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[OfertaSchema]:
    return oferta_service.listar(db, tenant_id)


@router.put("/{oferta_id}", response_model=OfertaSchema)
def atualizar_oferta(
    oferta_id: int,
    dados: OfertaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> OfertaSchema:
    return oferta_service.atualizar(db, tenant_id, ator_id, oferta_id, dados)


@router.post("/{oferta_id}/ativar", response_model=OfertaSchema)
def ativar_oferta(
    oferta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> OfertaSchema:
    return oferta_service.ativar(db, tenant_id, ator_id, oferta_id)


@router.post("/{oferta_id}/desativar", response_model=OfertaSchema)
def desativar_oferta(
    oferta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> OfertaSchema:
    return oferta_service.desativar(db, tenant_id, ator_id, oferta_id)


@router.delete("/{oferta_id}", status_code=204)
def excluir_oferta(
    oferta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    oferta_service.excluir(db, tenant_id, ator_id, oferta_id)


@router.post("/{oferta_id}/materiais", response_model=MaterialOfertaSchema, status_code=201)
async def enviar_material(
    oferta_id: int,
    arquivo: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MaterialOfertaSchema:
    conteudo = await arquivo.read()
    return oferta_service.salvar_material(
        db,
        tenant_id,
        ator_id,
        oferta_id,
        arquivo.filename or "arquivo",
        arquivo.content_type or "",
        conteudo,
    )
