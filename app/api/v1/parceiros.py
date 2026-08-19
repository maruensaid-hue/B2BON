from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_chave_api_atual, get_db, get_plan_limits_provider, limitar_por_chave_api
from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.tenant import Tenant
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.conta import FranquiaSchema
from app.schemas.parceiro import ProvisionarTenantRequestSchema
from app.schemas.tenant import DefinirLicencaRequestSchema, LicencaSchema, TenantSchema
from app.services import franquia_service, tenant_service
from app.services.errors import NaoAutorizado

router = APIRouter(
    prefix="/parceiros",
    tags=["parceiros"],
    dependencies=[Depends(get_chave_api_atual), Depends(limitar_por_chave_api())],
)


def _exigir_tenant_na_arvore(db: Session, chave: ChaveApiParceiro, tenant_id: str) -> None:
    if tenant_id != chave.tenant_id and not tenant_service.e_ancestral(db, chave.tenant_id, tenant_id):
        raise NaoAutorizado("Este tenant não pertence à sua árvore.")


@router.post("/tenants", response_model=TenantSchema, status_code=201)
def provisionar_tenant(
    dados: ProvisionarTenantRequestSchema,
    db: Session = Depends(get_db),
    chave: ChaveApiParceiro = Depends(get_chave_api_atual),
) -> TenantSchema:
    """Provisiona um Revendedor novo direto sob o Distribuidor dono da
    chave (Fase 2 da hierarquia, raio-X) — reaproveita
    `tenant_service.criar_tenant_inicial`, mesmo esqueleto usado por
    `POST /admin/tenants`. Cria o tenant + primeiro usuário admin numa
    chamada só; CRUD de usuário adicional fica fora desta entrega."""
    usuario_admin = tenant_service.criar_tenant_inicial(
        db,
        dados.tenant_id,
        dados.razao_social,
        dados.plano_id,
        dados.nome_admin,
        dados.email_admin,
        dados.senha_admin,
        dados.cnpj,
        tenant_pai_id=chave.tenant_id,
        tipo="revendedor",
        papel_primeiro_usuario="admin",
    )
    return db.query(Tenant).filter_by(id=usuario_admin.tenant_id).one()


@router.get("/tenants", response_model=list[TenantSchema])
def listar_tenants(db: Session = Depends(get_db), chave: ChaveApiParceiro = Depends(get_chave_api_atual)) -> list[TenantSchema]:
    return tenant_service.listar_subarvore(db, chave.tenant_id)


@router.put("/tenants/{tenant_id}/licenca", response_model=LicencaSchema)
def atualizar_licenca(
    tenant_id: str,
    dados: DefinirLicencaRequestSchema,
    db: Session = Depends(get_db),
    chave: ChaveApiParceiro = Depends(get_chave_api_atual),
) -> LicencaSchema:
    _exigir_tenant_na_arvore(db, chave, tenant_id)
    return tenant_service.atualizar_licenca(
        db, tenant_id, f"chave-api:{chave.id}", dados.plano_id, dados.status, dados.data_expiracao
    )


@router.get("/tenants/{tenant_id}/uso", response_model=FranquiaSchema)
def obter_uso(
    tenant_id: str,
    db: Session = Depends(get_db),
    chave: ChaveApiParceiro = Depends(get_chave_api_atual),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> FranquiaSchema:
    _exigir_tenant_na_arvore(db, chave, tenant_id)
    return FranquiaSchema(**franquia_service.obter_franquia(db, tenant_id, plan_limits))


@router.get("/tenants/{tenant_id}/billing", response_model=LicencaSchema)
def obter_billing(
    tenant_id: str, db: Session = Depends(get_db), chave: ChaveApiParceiro = Depends(get_chave_api_atual)
) -> LicencaSchema:
    _exigir_tenant_na_arvore(db, chave, tenant_id)
    return tenant_service.obter_licenca(db, tenant_id)
