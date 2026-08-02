from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db
from app.models.tenant import Tenant
from app.schemas.tenant import (
    CriarTenantRequestSchema,
    DefinirLicencaRequestSchema,
    LicencaSchema,
    TenantSchema,
)
from app.services import tenant_service

router = APIRouter(prefix="/admin/tenants", tags=["admin"], dependencies=[Depends(exigir_papel("super_admin"))])


@router.get("", response_model=list[TenantSchema])
def listar_tenants(db: Session = Depends(get_db)) -> list[TenantSchema]:
    """Visão cross-tenant — só super_admin (Onda A)."""
    return tenant_service.listar_tenants(db)


@router.post("", response_model=TenantSchema, status_code=201)
def criar_tenant(dados: CriarTenantRequestSchema, db: Session = Depends(get_db)) -> TenantSchema:
    """Onboarding de um novo tenant por um super_admin já autenticado —
    distinto do bootstrap do primeiro tenant (script, sem essa exigência
    circular de já ter um super_admin para criar o primeiro)."""
    usuario_admin = tenant_service.criar_tenant_inicial(
        db,
        dados.tenant_id,
        dados.razao_social,
        dados.plano_id,
        dados.nome_admin,
        dados.email_admin,
        dados.senha_admin,
        dados.cnpj,
    )
    return db.query(Tenant).filter_by(id=usuario_admin.tenant_id).one()


@router.get("/{tenant_id}/licenca", response_model=LicencaSchema)
def obter_licenca(tenant_id: str, db: Session = Depends(get_db)) -> LicencaSchema:
    return tenant_service.obter_licenca(db, tenant_id)


@router.put("/{tenant_id}/licenca", response_model=LicencaSchema)
def atualizar_licenca(
    tenant_id: str,
    dados: DefinirLicencaRequestSchema,
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> LicencaSchema:
    return tenant_service.atualizar_licenca(
        db, tenant_id, ator_id, dados.plano_id, dados.status, dados.data_expiracao
    )
