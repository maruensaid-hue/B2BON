from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_email_provider_do_tenant, get_llm_provider, get_tenant_id, get_whatsapp_provider
from app.llm.base import LLMProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.schemas.nps import (
    ConfiguracaoNpsSchema,
    ConfiguracaoNpsUpsertSchema,
    PesquisaNpsSchema,
    ResponderNpsRequestSchema,
)
from app.services import nps_service

router = APIRouter(prefix="/nps", tags=["nps"])


@router.get("/configuracao", response_model=ConfiguracaoNpsSchema)
def obter_configuracao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoNpsSchema:
    config = nps_service.obter_configuracao(db, tenant_id)
    return ConfiguracaoNpsSchema(dias_apos_reuniao_realizada=config.dias_apos_reuniao_realizada)


@router.put("/configuracao", response_model=ConfiguracaoNpsSchema)
def definir_configuracao(
    dados: ConfiguracaoNpsUpsertSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConfiguracaoNpsSchema:
    """Disparo de NPS configurável por marco (E11-H1)."""
    config = nps_service.definir_configuracao(db, tenant_id, dados.dias_apos_reuniao_realizada)
    return ConfiguracaoNpsSchema(dias_apos_reuniao_realizada=config.dias_apos_reuniao_realizada)


@router.post("/disparar-pendentes")
def disparar_pendentes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
    email: EmailProvider = Depends(get_email_provider_do_tenant),
) -> dict:
    """Dispatcher de NPS por dias-após-reunião — chamado por cron externo (E11-H1)."""
    return nps_service.disparar_pendentes(db, tenant_id, whatsapp, email)


@router.get("/responder/{token}", response_model=PesquisaNpsSchema)
def obter_pesquisa(token: str, db: Session = Depends(get_db)) -> PesquisaNpsSchema:
    """Endpoint público — o cliente vê a pesquisa a partir do link recebido."""
    return nps_service.obter_por_token(db, token)


@router.post("/responder/{token}", response_model=PesquisaNpsSchema)
def responder(
    token: str,
    dados: ResponderNpsRequestSchema,
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
    llm: LLMProvider = Depends(get_llm_provider),
) -> PesquisaNpsSchema:
    """Resposta pública, sem X-Tenant-Id — mesmo padrão de reagendamento/opt-out (E11-H1)."""
    return nps_service.responder(db, token, dados.nota, whatsapp, llm)
