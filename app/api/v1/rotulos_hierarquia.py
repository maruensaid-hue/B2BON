from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_db
from app.schemas.rotulo_hierarquia import AtualizarRotulosHierarquiaRequestSchema, RotuloTipoTenantSchema
from app.services import rotulo_hierarquia_service

router = APIRouter(prefix="/rotulos-hierarquia", tags=["rotulos-hierarquia"])


@router.get("", response_model=list[RotuloTipoTenantSchema])
def listar_rotulos(db: Session = Depends(get_db)) -> list[RotuloTipoTenantSchema]:
    """Lista pública (mesmo espírito de `GET /planos`) — qualquer tela que
    exiba o tipo de um tenant usa isso em vez do valor interno fixo
    (distribuidor/revendedor/cliente)."""
    return rotulo_hierarquia_service.listar(db)


@router.put("", response_model=list[RotuloTipoTenantSchema], dependencies=[Depends(exigir_papel("super_admin"))])
def atualizar_rotulos(
    dados: AtualizarRotulosHierarquiaRequestSchema, db: Session = Depends(get_db)
) -> list[RotuloTipoTenantSchema]:
    return rotulo_hierarquia_service.atualizar(
        db, dados.rotulo_distribuidor, dados.rotulo_revendedor, dados.rotulo_cliente
    )
