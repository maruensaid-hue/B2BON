from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_email_provider, get_tenant_id
from app.providers.channels.email.base import EmailProvider
from app.schemas.convite import (
    ConviteCadastroSchema,
    ConviteVitrineCriadoSchema,
    ConviteVitrineSchema,
    GerarConviteRequestSchema,
    GerarConviteVitrineRequestSchema,
)
from app.services import auth_service, tenant_service

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


@router.post(
    "/{codigo}/reativar", response_model=ConviteCadastroSchema, dependencies=[Depends(exigir_papel("super_admin", "admin"))]
)
def reativar_convite(
    codigo: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConviteCadastroSchema:
    return auth_service.reativar_convite(db, tenant_id, ator_id, codigo)


@router.delete("/{codigo}", status_code=204, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def excluir_convite(
    codigo: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> Response:
    auth_service.excluir_convite(db, tenant_id, ator_id, codigo)
    return Response(status_code=204)


@router.post("/vitrine", response_model=ConviteVitrineCriadoSchema, status_code=201)
def gerar_convite_vitrine(
    dados: GerarConviteVitrineRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> ConviteVitrineCriadoSchema:
    """Convida uma empresa nova para a Rede Social — sem exigir papel
    admin, qualquer usuário do tenant pode gerar (Onda H)."""
    convite = tenant_service.gerar_convite_vitrine(
        db, tenant_id, ator_id, dados.validade_horas, dados.email_destinatario, email
    )
    return ConviteVitrineCriadoSchema.model_validate(convite)


@router.get("/vitrine", response_model=list[ConviteVitrineSchema])
def listar_convites_vitrine(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ConviteVitrineSchema]:
    return tenant_service.listar_convites_vitrine(db, tenant_id)


@router.post("/vitrine/{codigo}/revogar", response_model=ConviteVitrineSchema)
def revogar_convite_vitrine(
    codigo: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConviteVitrineSchema:
    return tenant_service.revogar_convite_vitrine(db, tenant_id, ator_id, codigo)


@router.post("/vitrine/{codigo}/reativar", response_model=ConviteVitrineSchema)
def reativar_convite_vitrine(
    codigo: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConviteVitrineSchema:
    return tenant_service.reativar_convite_vitrine(db, tenant_id, ator_id, codigo)


@router.delete("/vitrine/{codigo}", status_code=204)
def excluir_convite_vitrine(
    codigo: str,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> Response:
    tenant_service.excluir_convite_vitrine(db, tenant_id, ator_id, codigo)
    return Response(status_code=204)
