import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_account_data_provider,
    get_contact_enrichment_provider,
    get_db,
    get_email_provider,
    get_graph_client,
    get_llm_provider,
    get_payment_provider,
    get_site_fetcher,
    get_usuario_atual,
    get_web_search_provider,
)
from app.core.config import settings
from app.core.rate_limit import limitar_por_ip
from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.models.licenca import Licenca
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.account_data.base import AccountDataProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.payment.base import PaymentProvider
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider
from app.providers.web_search.base import WebSearchProvider
from app.schemas.auth import (
    LicencaStatusResponseSchema,
    LoginGoogleRequestSchema,
    LoginRequestSchema,
    RecursosPlanoSchema,
    RegistrarRequestSchema,
    RegistrarVitrineRequestSchema,
    TokenResponseSchema,
    UsuarioSchema,
)
from app.services import auth_service, pagamento_licenca_service, tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _enviar_email_boas_vindas_primeiro_login(usuario: Usuario, email_provider: EmailProvider) -> None:
    try:
        corpo = (
            f"Olá, {usuario.nome}!\n\n"
            f"Que bom ter você usando a B2B ON! Você já tem acesso ao CRM, prospecção automatizada, "
            f"MAP (Motor de Alta Performance) e à rede social entre empresas.\n\n"
            f"Alguma dúvida? Assista o tutorial da plataforma, consulte a FAQ. Em breve também vamos "
            f"lançar uma plataforma de treinamento com conteúdo passo a passo sobre cada funcionalidade "
            f"e certificação para profissionais técnicos e usuários.\n\n"
            f"Não encontrou o que precisava? Fale com a nossa equipe de suporte em suporte@cyberfort.com.br."
        )
        email_provider.enviar(
            usuario.email, "Bem-vindo à B2B ON!", corpo, "B2B ON", settings.sendgrid_remetente_email,
            usuario.tenant_id,
        )
    except Exception:
        logger.warning("Falha ao enviar e-mail de boas-vindas pro usuário %s", usuario.id, exc_info=True)


def _resposta_token(
    usuario: Usuario,
    db: Session,
    checkout_url: str | None = None,
    primeiro_login: bool = False,
    email_provider: EmailProvider | None = None,
) -> TokenResponseSchema:
    licenca = db.query(Licenca).filter_by(tenant_id=usuario.tenant_id).one_or_none()
    tenant = db.query(Tenant).filter_by(id=usuario.tenant_id).one_or_none()
    plan_limits = NucleoPlanLimitsProvider(db)
    recursos_plano = RecursosPlanoSchema(
        ab_teste_cadencia=plan_limits.permite_ab_teste_cadencia(usuario.tenant_id),
        auto_aprovacao=plan_limits.permite_auto_aprovacao(usuario.tenant_id),
        webhook_relatorio=plan_limits.permite_webhook_relatorio(usuario.tenant_id),
        api_parceiros=plan_limits.permite_api_parceiros(usuario.tenant_id),
        subtenants=plan_limits.permite_subtenants(usuario.tenant_id),
        registro_oportunidade=plan_limits.permite_registro_oportunidade(usuario.tenant_id),
        retencao_dias_relatorio=plan_limits.obter_retencao_dias_relatorio(usuario.tenant_id),
    )
    usuario_schema = UsuarioSchema.model_validate(usuario).model_copy(
        update={
            "tenant_tipo": tenant.tipo if tenant is not None else "cliente",
            "recursos_plano": recursos_plano,
        }
    )
    if primeiro_login and email_provider is not None:
        _enviar_email_boas_vindas_primeiro_login(usuario, email_provider)
    return TokenResponseSchema(
        access_token=auth_service.gerar_token(usuario),
        usuario=usuario_schema,
        tem_licenca_ativa=licenca is not None and licenca.status == "ativa",
        checkout_url=checkout_url,
        primeiro_login=primeiro_login,
    )


@router.post("/login", response_model=TokenResponseSchema, dependencies=[Depends(limitar_por_ip())])
def login(
    dados: LoginRequestSchema, db: Session = Depends(get_db), email: EmailProvider = Depends(get_email_provider)
) -> TokenResponseSchema:
    usuario, primeiro_login = auth_service.autenticar_senha(db, dados.email, dados.senha)
    return _resposta_token(usuario, db, primeiro_login=primeiro_login, email_provider=email)


@router.post("/google", response_model=TokenResponseSchema, dependencies=[Depends(limitar_por_ip())])
def login_google(
    dados: LoginGoogleRequestSchema,
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> TokenResponseSchema:
    usuario, primeiro_login = auth_service.autenticar_google(db, dados.id_token)
    return _resposta_token(usuario, db, primeiro_login=primeiro_login, email_provider=email)


@router.post(
    "/registrar", response_model=TokenResponseSchema, status_code=201, dependencies=[Depends(limitar_por_ip())]
)
def registrar(
    dados: RegistrarRequestSchema, db: Session = Depends(get_db), email: EmailProvider = Depends(get_email_provider)
) -> TokenResponseSchema:
    usuario = auth_service.registrar_com_convite(
        db, dados.codigo_convite, dados.nome, dados.email, dados.senha, dados.aceite_termos
    )
    return _resposta_token(usuario, db, primeiro_login=True, email_provider=email)


@router.post(
    "/registrar-vitrine",
    response_model=TokenResponseSchema,
    status_code=201,
    dependencies=[Depends(limitar_por_ip())],
)
def registrar_vitrine(
    dados: RegistrarVitrineRequestSchema,
    db: Session = Depends(get_db),
    payment_provider: PaymentProvider = Depends(get_payment_provider),
    llm: LLMProvider = Depends(get_llm_provider),
    site_fetcher: SiteFetcher = Depends(get_site_fetcher),
    web_search: WebSearchProvider = Depends(get_web_search_provider),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    contact_enrichment: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider),
    graph: Neo4jClient = Depends(get_graph_client),
    email: EmailProvider = Depends(get_email_provider),
) -> TokenResponseSchema:
    """Aceite público de convite-vitrine — cria o tenant novo, já loga, e
    abre a cobrança do plano escolhido (Onda H + raio-X de produção). Sem
    autenticação prévia, como `/registrar`. A licença nasce
    `pendente_pagamento`; o frontend redireciona pro `checkout_url`
    devolvido aqui. Também cadastra a empresa como prospect no CRM de
    quem enviou o convite, já tentando enriquecer via site/contatos."""
    usuario, checkout_url = tenant_service.criar_tenant_vitrine(
        db,
        dados.codigo_convite,
        dados.razao_social,
        dados.nome_admin,
        dados.email_admin,
        dados.senha_admin,
        dados.aceite_termos,
        dados.plano_id,
        payment_provider,
        llm,
        site_fetcher,
        web_search,
        account_data,
        contact_enrichment,
        graph,
        dados.cnpj,
    )
    return _resposta_token(usuario, db, checkout_url, primeiro_login=True, email_provider=email)


@router.get("/eu", response_model=UsuarioSchema)
def eu(usuario: Usuario = Depends(get_usuario_atual)) -> UsuarioSchema:
    return usuario


@router.get("/licenca-status", response_model=LicencaStatusResponseSchema)
def licenca_status(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)) -> LicencaStatusResponseSchema:
    """Usado pela tela de retorno do checkout (Mercado Pago) pra saber
    quando parar de esperar o webhook confirmar o pagamento."""
    return LicencaStatusResponseSchema(status=pagamento_licenca_service.status_licenca(db, usuario.tenant_id))


@router.post("/declarar-pagamento", response_model=LicencaStatusResponseSchema)
def declarar_pagamento(
    usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)
) -> LicencaStatusResponseSchema:
    """Autoatendimento "já paguei" (raio-X 2026-09-09) — deliberadamente sem
    `exigir_licenca_ativa`, já que é exatamente pra quem está suspenso
    reativar o próprio acesso enquanto o pagamento (boleto/cartão tardio)
    ainda está compensando. Ver `pagamento_licenca_service.declarar_pagamento`
    pra carência própria de 3 dias que se abre a partir daqui."""
    licenca = pagamento_licenca_service.declarar_pagamento(db, usuario.tenant_id)
    return LicencaStatusResponseSchema(status=licenca.status)
