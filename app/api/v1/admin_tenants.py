from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    exigir_gestor_do_tenant,
    get_ator_id,
    get_db,
    get_email_provider,
    get_usuario_atual,
    permitir_gestao_hierarquica,
)
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.schemas.tenant import (
    CriarTenantRequestSchema,
    DefinirLicencaRequestSchema,
    LicencaSchema,
    TenantSchema,
)
from app.services import tenant_service
from app.services.errors import NaoAutorizado

router = APIRouter(prefix="/admin/tenants", tags=["admin"], dependencies=[Depends(permitir_gestao_hierarquica)])


@router.get("", response_model=list[TenantSchema])
def listar_tenants(db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)) -> list[TenantSchema]:
    """Visão cross-tenant — super_admin vê tudo; admin de um tenant
    distribuidor/revendedor vê a própria subárvore (raio-X: hierarquia)."""
    return tenant_service.listar_tenants_visiveis(db, usuario)


@router.post("", response_model=TenantSchema, status_code=201)
def criar_tenant(
    dados: CriarTenantRequestSchema,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
    email: EmailProvider = Depends(get_email_provider),
) -> TenantSchema:
    """Onboarding de um novo tenant por um gestor já autenticado — distinto
    do bootstrap do primeiro tenant (script, sem essa exigência circular de
    já ter um super_admin para criar o primeiro).

    `tenant_pai_id` None só pode ser criado por super_admin (tenant
    top-level); com `tenant_pai_id` preenchido, quem chama precisa ser
    exatamente o admin desse tenant pai (Distribuidor criando Revendedor,
    Revendedor criando Cliente) ou super_admin. O primeiro usuário do
    tenant novo sempre nasce `papel="admin"`, nunca `super_admin` — ver
    `tenant_service.criar_tenant_inicial`."""
    if usuario.papel != "super_admin":
        if dados.tenant_pai_id is None or dados.tenant_pai_id != usuario.tenant_id:
            raise NaoAutorizado("Você só pode criar tenants diretamente sob o seu próprio tenant.")

    usuario_admin = tenant_service.criar_tenant_inicial(
        db,
        dados.tenant_id,
        dados.razao_social,
        dados.plano_id,
        dados.nome_admin,
        dados.email_admin,
        dados.senha_admin,
        dados.cnpj,
        tenant_pai_id=dados.tenant_pai_id,
        tipo=dados.tipo,
        modo_cobranca=dados.modo_cobranca,
        papel_primeiro_usuario="admin",
        email_provider=email,
    )
    return db.query(Tenant).filter_by(id=usuario_admin.tenant_id).one()


@router.get("/{tenant_id}/licenca", response_model=LicencaSchema, dependencies=[Depends(exigir_gestor_do_tenant)])
def obter_licenca(tenant_id: str, db: Session = Depends(get_db)) -> LicencaSchema:
    return tenant_service.obter_licenca(db, tenant_id)


@router.put("/{tenant_id}/licenca", response_model=LicencaSchema, dependencies=[Depends(exigir_gestor_do_tenant)])
def atualizar_licenca(
    tenant_id: str,
    dados: DefinirLicencaRequestSchema,
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> LicencaSchema:
    return tenant_service.atualizar_licenca(
        db, tenant_id, ator_id, dados.plano_id, dados.status, dados.data_expiracao
    )
