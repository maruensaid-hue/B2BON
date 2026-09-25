from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.core.rate_limit import limitar_por_ip
from app.schemas.captura_lead import CriarLeadPublicoRequestSchema, InfoCapturaLeadSchema, LinkCapturaLeadSchema
from app.services import link_captura_lead_service

router = APIRouter(prefix="/captura-lead", tags=["captura-lead"])


@router.get("/config", response_model=LinkCapturaLeadSchema)
def obter_config(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> LinkCapturaLeadSchema:
    """Autenticado — a tela de Configuração usa isso pra mostrar (e gerar,
    na primeira vez) o link permanente do próprio tenant."""
    return LinkCapturaLeadSchema.model_validate(link_captura_lead_service.obter_ou_criar(db, tenant_id))


@router.get("/{codigo}/info", response_model=InfoCapturaLeadSchema)
def obter_info_publica(codigo: str, db: Session = Depends(get_db)) -> InfoCapturaLeadSchema:
    """Pública, sem autenticação — a tela de captura usa isso só pra saber
    o nome da empresa a exibir antes do formulário."""
    tenant_id = link_captura_lead_service.resolver_tenant_por_codigo(db, codigo)
    return InfoCapturaLeadSchema(nome_exibicao=link_captura_lead_service.obter_nome_exibicao(db, tenant_id))


@router.post(
    "/{codigo}",
    status_code=201,
    # Sem convite/portão nenhum (é um link de anúncio, potencialmente
    # exposto em massa) — mesmo limite apertado de `/auth/registrar-publico`.
    dependencies=[Depends(limitar_por_ip(max_tentativas=3, janela_segundos=600))],
)
def criar_lead_publico(
    codigo: str, dados: CriarLeadPublicoRequestSchema, db: Session = Depends(get_db)
) -> dict:
    link_captura_lead_service.criar_lead_publico(
        db,
        codigo=codigo,
        nome_empresa=dados.nome_empresa,
        cnpj=dados.cnpj,
        nome_contato=dados.nome_contato,
        email_contato=dados.email_contato,
        telefone_contato=dados.telefone_contato,
        cargo_contato=dados.cargo_contato,
    )
    return {"recebido": True}
