from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id
from app.schemas.convite import ConviteCadastroSchema, GerarConviteRequestSchema
from app.services import auth_service

router = APIRouter(prefix="/convites", tags=["convites"])


@router.post(
    "", response_model=ConviteCadastroSchema, status_code=201, dependencies=[Depends(exigir_papel("super_admin", "admin"))]
)
def gerar_convite(
    dados: GerarConviteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConviteCadastroSchema:
    return auth_service.gerar_convite(db, tenant_id, ator_id, dados.papel_concedido, dados.validade_horas)


@router.get("", response_model=list[ConviteCadastroSchema])
def listar_convites(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ConviteCadastroSchema]:
    return auth_service.listar_convites(db, tenant_id)


@router.post(
    "/{codigo}/revogar", response_model=ConviteCadastroSchema, dependencies=[Depends(exigir_papel("super_admin", "admin"))]
)
def revogar_convite(
    codigo: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConviteCadastroSchema:
    return auth_service.revogar_convite(db, tenant_id, ator_id, codigo)
