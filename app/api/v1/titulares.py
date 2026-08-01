from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.titular import (
    BuscaTitularResponseSchema,
    EliminarTitularResponseSchema,
    ExportacaoTitularResponseSchema,
)
from app.services import titular_service

router = APIRouter(prefix="/titulares", tags=["titulares"])


@router.get("/buscar", response_model=BuscaTitularResponseSchema)
def buscar_titular(
    identificador: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> BuscaTitularResponseSchema:
    """Busca de titular por identificadores (E9-H3)."""
    return BuscaTitularResponseSchema(**titular_service.buscar(db, tenant_id, identificador))


@router.get("/exportar", response_model=ExportacaoTitularResponseSchema)
def exportar_titular(
    identificador: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ExportacaoTitularResponseSchema:
    """Exportação dos dados tratados (E9-H3)."""
    return ExportacaoTitularResponseSchema(**titular_service.exportar(db, tenant_id, identificador))


@router.delete("", response_model=EliminarTitularResponseSchema)
def eliminar_titular(
    identificador: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> EliminarTitularResponseSchema:
    """Eliminação com preservação apenas do registro mínimo de supressão (E9-H3)."""
    return EliminarTitularResponseSchema(**titular_service.eliminar(db, tenant_id, ator_id, identificador))
