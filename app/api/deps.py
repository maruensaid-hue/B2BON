from collections.abc import Generator

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.graph.client import Neo4jClient
from app.core.config import settings
from app.integrations.site_fetcher import SiteFetcher, buscar_conteudo_site
from app.llm.claude_provider import ClaudeProvider
from app.providers.account_data.base import AccountDataProvider
from app.providers.account_data.receita_federal import ReceitaFederalCNPJProvider
from app.providers.calendar.base import CalendarProvider
from app.providers.calendar.google import GoogleCalendarProvider
from app.providers.calendar.stub import StubCalendarProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.email.smtp import SmtpEmailProvider
from app.providers.channels.email.stub import StubEmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.channels.whatsapp.meta import MetaWhatsAppProvider
from app.providers.channels.whatsapp.stub import StubWhatsAppProvider
from app.providers.crm.base import CrmProvider
from app.providers.crm.stub import StubCrmProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.providers.email_validation.stub import StubEmailVerificationProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.providers.rede_social.base import RedeSocialProvider
from app.providers.rede_social.stub import StubRedeSocialProvider


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_graph_client() -> Neo4jClient:
    return Neo4jClient()


def get_llm_provider() -> ClaudeProvider:
    return ClaudeProvider()


def get_site_fetcher() -> SiteFetcher:
    return buscar_conteudo_site


def get_account_data_provider(db: Session = Depends(get_db)) -> AccountDataProvider:
    return ReceitaFederalCNPJProvider(db)


def get_plan_limits_provider() -> PlanLimitsProvider:
    # CoreApiPlanLimitsProvider entra aqui quando a integração com o núcleo
    # existir (Seção 11 da especificação). Até lá, todo ambiente usa o stub.
    return StubPlanLimitsProvider()


def get_whatsapp_provider() -> WhatsAppProvider:
    # Real (Meta) quando houver credenciais configuradas; senão, stub de
    # dev/teste. WhatsApp é a única porta de envio permitida (E3-H2).
    if settings.whatsapp_access_token:
        return MetaWhatsAppProvider()
    return StubWhatsAppProvider()


def get_email_provider() -> EmailProvider:
    if settings.smtp_host:
        return SmtpEmailProvider()
    return StubEmailProvider()


def get_calendar_provider() -> CalendarProvider:
    if settings.google_calendar_access_token:
        return GoogleCalendarProvider()
    return StubCalendarProvider()


def get_crm_provider() -> CrmProvider:
    # CoreApiCrmProvider entra aqui quando o núcleo expuser a API de
    # oportunidades. Até lá, todo ambiente (dev e testes) usa o stub — CRM é
    # dado do núcleo, mesma regra de fronteira do PlanLimitsProvider.
    return StubCrmProvider()


def get_rede_social_provider() -> RedeSocialProvider:
    # CoreApiRedeSocialProvider entra aqui quando o núcleo expuser a API da
    # Rede Social B2B. Até lá, todo ambiente (dev e testes) usa o stub — é
    # dado do núcleo, mesma regra de fronteira do CrmProvider.
    return StubRedeSocialProvider()


def get_email_validation_provider() -> EmailVerificationProvider:
    # ExternalEmailVerificationProvider entra aqui quando uma integração
    # real de verificação de e-mail for contratada. Até lá, todo ambiente
    # usa o stub (checagem de sintaxe + domínios conhecidos).
    return StubEmailVerificationProvider()


def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-Id")) -> str:
    """Identidade do assinante — propagada pelo núcleo B2B ON via gateway.

    Placeholder até a integração real de autenticação existir.
    """
    return x_tenant_id


def get_ator_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> str | None:
    """Usuário humano que está agindo — usado para atribuição na auditoria."""
    return x_user_id
