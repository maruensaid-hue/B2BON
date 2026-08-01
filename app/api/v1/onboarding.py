from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.onboarding import OnboardingStatusSchema
from app.services import comunicacao_service, icp_service, oferta_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatusSchema)
def status_onboarding(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> OnboardingStatusSchema:
    icp_ativo = icp_service.existe_icp_ativo(db, tenant_id)
    oferta_cadastrada = oferta_service.existe_oferta_ativa(db, tenant_id)
    comunicacao_configurada = comunicacao_service.obter(db, tenant_id) is not None

    orientacao = []
    if not icp_ativo:
        orientacao.append("Crie e ative um ICP para que o motor possa prospectar.")
    if not oferta_cadastrada:
        orientacao.append("Cadastre ao menos uma oferta.")
    if not comunicacao_configurada:
        orientacao.append("Configure tom de voz e restrições de comunicação.")

    return OnboardingStatusSchema(
        icp_ativo=icp_ativo,
        oferta_cadastrada=oferta_cadastrada,
        comunicacao_configurada=comunicacao_configurada,
        pronto_para_prospeccao=icp_ativo and oferta_cadastrada and comunicacao_configurada,
        orientacao=orientacao,
    )
