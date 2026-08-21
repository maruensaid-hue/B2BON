from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_email_provider, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.schemas.convite import (
    ConviteCadastroSchema,
    ConviteVitrineCriadoSchema,
    ConviteVitrineInfoSchema,
    ConviteVitrineSchema,
    GerarConviteRequestSchema,
    GerarConviteVitrineRequestSchema,
)
from app.services import auth_service, tenant_service
from app.services.errors import NaoAutorizado

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
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> ConviteVitrineCriadoSchema:
    """Convida uma empresa nova para a Rede Social — sem exigir papel
    admin, qualquer usuário do tenant pode gerar (Onda H). Exceção:
    `gratuito=True` (raio-X, concede o plano "Teste" sem checkout) só
    pra admin/super_admin — sem essa trava, qualquer usuário comum
    poderia gerar contas gratuitas ilimitadas pra terceiros."""
    if dados.gratuito and usuario.papel not in ("super_admin", "admin"):
        raise NaoAutorizado("Só admin pode gerar convite gratuito.")
    convite = tenant_service.gerar_convite_vitrine(
        db, tenant_id, ator_id, dados.validade_horas, dados.email_destinatario, email, dados.gratuito
    )
    return ConviteVitrineCriadoSchema.model_validate(convite)


@router.get("/vitrine/{codigo}/info", response_model=ConviteVitrineInfoSchema)
def obter_info_convite_vitrine(codigo: str, db: Session = Depends(get_db)) -> ConviteVitrineInfoSchema:
    """Pública, sem autenticação — a tela de cadastro (`ConviteVitrine.tsx`)
    usa isso pra saber, antes de qualquer coisa, se esconde o seletor de
    plano/checkout (convite gratuito) ou mostra normalmente."""
    return ConviteVitrineInfoSchema.model_validate(tenant_service.obter_info_convite_vitrine(db, codigo))


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
