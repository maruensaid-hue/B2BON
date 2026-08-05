from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db, get_tenant_id
from app.models.usuario import Usuario
from app.schemas.auth import UsuarioSchema

router = APIRouter(
    prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(exigir_papel("admin", "super_admin"))]
)


@router.get("", response_model=list[UsuarioSchema])
def listar_usuarios(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[UsuarioSchema]:
    """Lista enxuta dos usuários do próprio tenant — usada para atribuir
    vendedor a uma conta e para o filtro por vendedor no MAP de contas.
    Restrita a admin/super_admin (quem gerencia atribuições), não ao
    vendedor comum."""
    return db.query(Usuario).filter_by(tenant_id=tenant_id, ativo=True).order_by(Usuario.nome).all()
