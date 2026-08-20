import hashlib
from collections.abc import Generator
from datetime import UTC, datetime

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.graph.client import Neo4jClient
from app.core.config import settings
from app.core.rate_limit import limitador_parceiros
from app.integrations.brasilapi_client import BrasilApiClient, consultar_cnpj_brasilapi
from app.integrations.site_fetcher import SiteFetcher, buscar_conteudo_site
from app.llm.claude_provider import ClaudeProvider
from app.models.chave_api_parceiro import ChaveApiParceiro
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp
from app.models.licenca import Licenca
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.account_data.base import AccountDataProvider
from app.providers.account_data.receita_federal import ReceitaFederalCNPJProvider
from app.providers.calendar.base import CalendarProvider
from app.providers.calendar.google import GoogleCalendarProvider
from app.providers.calendar.stub import StubCalendarProvider
from app.providers.meeting_bot.base import MeetingBotProvider
from app.providers.meeting_bot.recall import RecallMeetingBotProvider
from app.providers.meeting_bot.stub import StubMeetingBotProvider
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.contact_enrichment.desativado import ContactEnrichmentDesativadoProvider
from app.providers.contact_enrichment.lusha import LushaContactEnrichmentProvider
from app.providers.contact_enrichment.stub import StubContactEnrichmentProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.email.desativado import EmailDesativadoProvider
from app.providers.channels.email.sendgrid import SendGridEmailProvider
from app.providers.channels.email.smtp import SmtpEmailProvider
from app.providers.channels.email.stub import StubEmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.channels.whatsapp.meta import MetaWhatsAppProvider
from app.providers.channels.whatsapp.stub import StubWhatsAppProvider
from app.providers.crm.base import CrmProvider
from app.providers.crm.nucleo import NucleoCrmProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.providers.email_validation.stub import StubEmailVerificationProvider
from app.providers.payment.base import PaymentProvider
from app.providers.payment.mercadopago import MercadoPagoProvider
from app.providers.payment.stub import StubPaymentProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider
from app.providers.rede_social.base import RedeSocialProvider
from app.providers.rede_social.nucleo import NucleoRedeSocialProvider
from app.providers.web_search.base import WebSearchProvider
from app.providers.web_search.brave import BraveSearchProvider
from app.providers.web_search.desativado import WebSearchDesativadoProvider
from app.providers.web_search.stub import StubWebSearchProvider
from app.services import auth_service, tenant_service
from app.services.errors import NaoAutenticado, NaoAutorizado


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


def get_contact_enrichment_provider() -> ContactEnrichmentProvider:
    if settings.contact_enrichment_api_key:
        return LushaContactEnrichmentProvider(settings.contact_enrichment_api_key)
    if settings.e_ambiente_producao:
        # `mapear_decisores` chama `buscar_contatos` sem nenhuma trava — o
        # stub de dados fictícios não pode vazar pra fora de dev/teste
        # (ver ContactEnrichmentDesativadoProvider).
        return ContactEnrichmentDesativadoProvider()
    return StubContactEnrichmentProvider()


def get_web_search_provider() -> WebSearchProvider:
    if settings.brave_search_api_key:
        return BraveSearchProvider()
    if settings.e_ambiente_producao:
        # StubWebSearchProvider fabrica um domínio plausível a partir da
        # query — em produção sem chave real, isso salvava um site
        # inexistente na conta (ver WebSearchDesativadoProvider).
        return WebSearchDesativadoProvider()
    return StubWebSearchProvider()


def get_brasilapi_client() -> BrasilApiClient:
    return consultar_cnpj_brasilapi


def get_plan_limits_provider(db: Session = Depends(get_db)) -> PlanLimitsProvider:
    # Onda A: porta implementada de verdade — licença/plano nascem no
    # próprio núcleo (mesma base do PREDATOR). StubPlanLimitsProvider
    # continua existindo só para os testes (dependency override).
    return NucleoPlanLimitsProvider(db)


def get_email_provider() -> EmailProvider:
    # SendGrid tem prioridade sobre SMTP — permite migrar sem precisar
    # remover as env vars de SMTP do Render no mesmo passo.
    if settings.sendgrid_api_key:
        return SendGridEmailProvider()
    if settings.smtp_host:
        return SmtpEmailProvider()
    if settings.e_ambiente_producao:
        # StubEmailProvider sempre reporta sucesso mesmo sem enviar nada
        # de verdade — em produção sem SMTP configurado, isso fazia o
        # convite de empresa parecer enviado quando não saía nada.
        return EmailDesativadoProvider()
    return StubEmailProvider()


def get_payment_provider() -> PaymentProvider:
    # Real (Mercado Pago) quando houver credencial configurada; senão,
    # stub de dev/teste (cadastro self-service com escolha de plano).
    if settings.mercadopago_access_token:
        return MercadoPagoProvider()
    return StubPaymentProvider()


def get_calendar_provider() -> CalendarProvider:
    if settings.google_calendar_access_token:
        return GoogleCalendarProvider()
    return StubCalendarProvider()


def get_meeting_bot_provider() -> MeetingBotProvider:
    if settings.recall_api_key:
        return RecallMeetingBotProvider()
    return StubMeetingBotProvider()


def get_crm_provider(db: Session = Depends(get_db)) -> CrmProvider:
    # Onda B: porta implementada de verdade — CRM Core nasce no próprio
    # núcleo (mesma base do PREDATOR). StubCrmProvider continua existindo
    # só para os testes (dependency override).
    return NucleoCrmProvider(db)


def get_rede_social_provider(db: Session = Depends(get_db)) -> RedeSocialProvider:
    # Onda C: porta implementada de verdade — Rede Social B2B nasce no
    # próprio núcleo (mesma base do PREDATOR). StubRedeSocialProvider
    # continua existindo só para os testes (dependency override).
    return NucleoRedeSocialProvider(db)


def get_email_validation_provider() -> EmailVerificationProvider:
    # ExternalEmailVerificationProvider entra aqui quando uma integração
    # real de verificação de e-mail for contratada. Até lá, todo ambiente
    # usa o stub (checagem de sintaxe + domínios conhecidos).
    return StubEmailVerificationProvider()


def get_usuario_atual(
    authorization: str | None = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> Usuario:
    """Usuário autenticado por JWT (Onda A) — substitui o antigo trust cru
    dos headers X-Tenant-Id/X-User-Id, fechando o risco já documentado no
    manual técnico do PREDATOR.

    Header opcional no parâmetro (em vez de obrigatório) para que a
    ausência completa do header também caia em 401 — não em 422, que é o
    que o FastAPI devolveria sozinho para um `Header(...)` obrigatório
    faltante, misturando "não autenticado" com "corpo/parâmetro
    inválido".
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise NaoAutenticado("Cabeçalho Authorization deve ser 'Bearer <token>'.")
    token = authorization[len("Bearer ") :]
    return auth_service.validar_token(db, token)


def get_tenant_id(usuario: Usuario = Depends(get_usuario_atual)) -> str:
    """Identidade do assinante — derivada do usuário autenticado (Onda A)."""
    return usuario.tenant_id


def resolver_whatsapp_provider(tenant_id: str, db: Session) -> WhatsAppProvider:
    """Raio-X de produção: número de WhatsApp por tenant, não mais um
    único número compartilhado por toda a plataforma (um cliente
    prospectando mal não pode mais fazer todo mundo perder WhatsApp
    junto). Prioridade: 1) credencial própria do tenant
    (`ConfiguracaoWhatsApp`); 2) fallback legado — o token global único,
    só existe para não quebrar quem ainda não migrou; 3) stub de
    dev/teste.

    Função simples (não `Depends`) de propósito — os dispatchers de cron
    (`cron.py`) iteram sobre todos os tenants numa única requisição sem
    usuário autenticado (só o segredo de cron), então precisam resolver o
    provider tenant a tenant dentro do loop, não uma vez só no nível da
    rota como `get_whatsapp_provider` (que depende de `get_tenant_id`, e
    portanto de um JWT que o cron não tem)."""
    config_tenant = db.query(ConfiguracaoWhatsApp).filter_by(tenant_id=tenant_id).one_or_none()
    if config_tenant is not None:
        return MetaWhatsAppProvider(
            config_tenant.access_token, config_tenant.phone_number_id, config_tenant.business_account_id
        )
    if settings.whatsapp_access_token:
        return MetaWhatsAppProvider(
            settings.whatsapp_access_token, settings.whatsapp_phone_number_id, settings.whatsapp_business_account_id
        )
    return StubWhatsAppProvider()


def get_whatsapp_provider(
    tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)
) -> WhatsAppProvider:
    return resolver_whatsapp_provider(tenant_id, db)


def get_ator_id(usuario: Usuario = Depends(get_usuario_atual)) -> str | None:
    """Usuário humano que está agindo — usado para atribuição na auditoria."""
    return str(usuario.id)


_PROFUNDIDADE_MAXIMA_HIERARQUIA = 5


def exigir_licenca_ativa(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    """Trava os módulos pagos (PREDATOR/CRM/MAP) para tenants sem licença
    ativa — é o que distingue um cliente de uma empresa que só entrou pela
    Rede Social via convite (Onda H). `/rede-social/*` fica de fora
    deliberadamente: é a única coisa que uma conta sem licença pode usar.

    Tenant `modo_cobranca == "consolidada"` (raio-X: hierarquia de
    distribuidores) não tem `data_expiracao` própria relevante — sobe a
    cadeia de `tenant_pai_id` até achar quem realmente paga (`"direta"`
    ou sem pai) e checa a licença desse tenant."""
    tenant_a_checar_id = tenant_id
    for _ in range(_PROFUNDIDADE_MAXIMA_HIERARQUIA):
        tenant = db.query(Tenant).filter_by(id=tenant_a_checar_id).one_or_none()
        if tenant is None or tenant.modo_cobranca != "consolidada" or tenant.tenant_pai_id is None:
            break
        tenant_a_checar_id = tenant.tenant_pai_id

    licenca = db.query(Licenca).filter_by(tenant_id=tenant_a_checar_id).one_or_none()
    if licenca is None or licenca.status != "ativa":
        raise NaoAutorizado("Este recurso exige uma licença ativa.")


def exigir_papel(*papeis: str):
    """Dependency factory para proteger rotas administrativas por papel
    (ex.: Depends(exigir_papel("super_admin"))) — Onda A."""

    def _dependencia(usuario: Usuario = Depends(get_usuario_atual)) -> Usuario:
        if usuario.papel not in papeis:
            raise NaoAutorizado("Você não tem permissão para executar esta ação.")
        return usuario

    return _dependencia


def exigir_gestor_do_tenant(
    tenant_id: str,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    """Autoriza super_admin (sempre) ou um admin do próprio tenant alvo ou
    de um tenant ancestral dele (Distribuidor gerenciando um Revendedor/
    Cliente abaixo, Revendedor gerenciando seu Cliente) — generaliza
    `exigir_papel`, que só sabe checar papel plano, sem noção de hierarquia
    entre tenants. `tenant_id` é injetado automaticamente pelo FastAPI a
    partir do path param de mesmo nome na rota."""
    if usuario.papel == "super_admin":
        return usuario
    if usuario.papel == "admin" and (usuario.tenant_id == tenant_id or tenant_service.e_ancestral(db, usuario.tenant_id, tenant_id)):
        return usuario
    raise NaoAutorizado("Você não tem permissão para gerenciar este tenant.")


def permitir_gestao_hierarquica(
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    """Nível de router, sem `{tenant_id}` no path ainda (ex.: listagem
    cross-tenant) — só filtra quem PODE entrar; o escopo real (quais
    tenants aparecem) é aplicado dentro do handler via
    `tenant_service.listar_tenants_visiveis`."""
    if usuario.papel == "super_admin":
        return usuario
    tenant_do_usuario = db.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none()
    if usuario.papel == "admin" and tenant_do_usuario is not None and tenant_do_usuario.tipo in {"distribuidor", "revendedor"}:
        return usuario
    raise NaoAutorizado("Você não tem permissão para gerenciar tenants.")


def exigir_admin_distribuidor(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> Usuario:
    """Chave de API e webhook de saída (Fase 2 da hierarquia, raio-X) são
    exclusivos de admin de tenant `tipo="distribuidor"` — Revendedor
    continua só no painel via `permitir_gestao_hierarquica` (decisão
    validada com o usuário: reduz a superfície de risco desta primeira
    entrega da API externa)."""
    tenant = db.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none()
    if usuario.papel == "admin" and tenant is not None and tenant.tipo == "distribuidor":
        return usuario
    raise NaoAutorizado("Recurso exclusivo de administradores de tenant Distribuidor.")


def get_chave_api_atual(
    authorization: str | None = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> ChaveApiParceiro:
    """Autenticação de máquina (Fase 2 da hierarquia, raio-X) — o próprio
    sistema do Distribuidor chamando `/parceiros/*`, sem humano logado.
    Mesmo formato de header do JWT (`Bearer <segredo>`), mas resolvido por
    hash de API key, não por `auth_service.validar_token`."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise NaoAutenticado("Cabeçalho Authorization deve ser 'Bearer <chave>'.")
    chave_hash = hashlib.sha256(authorization[len("Bearer ") :].encode()).hexdigest()
    chave = db.query(ChaveApiParceiro).filter_by(chave_hash=chave_hash, revogada_em=None).one_or_none()
    if chave is None:
        raise NaoAutenticado("Chave de API inválida ou revogada.")
    chave.ultimo_uso_em = datetime.now(UTC)
    db.commit()
    return chave


def limitar_por_chave_api(max_tentativas: int = 100, janela_segundos: int = 60):
    """Chave do limite = id da credencial, não IP (tráfego de parceiro vem
    de servidor fixo do lado deles, IP não distingue abuso de uso legítimo
    em rajada) — mesmo `LimitadorEmMemoria` de `limitar_por_ip`, bucket
    próprio (`limitador_parceiros`)."""

    def _dependencia(chave: ChaveApiParceiro = Depends(get_chave_api_atual)) -> None:
        limitador_parceiros.checar(f"chave-api:{chave.id}", max_tentativas, janela_segundos)

    return _dependencia
