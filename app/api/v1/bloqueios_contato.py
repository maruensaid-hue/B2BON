from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id
from app.schemas.bloqueio_contato import BloqueioContatoSchema
from app.services import bloqueio_contato_service

router = APIRouter(prefix="/bloqueios-contato", tags=["bloqueios-contato"])


@router.get("", response_model=list[BloqueioContatoSchema])
def listar_bloqueios(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[BloqueioContatoSchema]:
    """Quem pediu para não receber mais nada (todas as campanhas da empresa)."""
    return bloqueio_contato_service.listar(db, tenant_id)


@router.delete("/{bloqueio_id}", status_code=204, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def liberar_bloqueio(
    bloqueio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    """Desfaz um bloqueio (ex.: marcado por engano). Só admin."""
    bloqueio_contato_service.liberar(db, tenant_id, ator_id, bloqueio_id)
