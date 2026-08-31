import logging

import sentry_sdk
from fastapi import APIRouter, BackgroundTasks, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import (
    get_account_data_provider,
    get_contact_enrichment_provider,
    get_db,
    get_email_provider,
    get_email_validation_provider,
    get_graph_client,
    get_llm_provider,
    get_plan_limits_provider,
    get_site_fetcher,
    get_web_search_provider,
    resolver_email_provider,
    resolver_whatsapp_provider,
)
from app.core.config import settings
from app.db.session import SessionLocal
from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.models.tenant import Tenant
from app.providers.account_data.base import AccountDataProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.providers.web_search.base import WebSearchProvider
from app.services import (
    campanha_service,
    cnpj_recorte_service,
    enriquecimento_fila_service,
    envio_service,
    nps_service,
    relatorio_service,
    reuniao_service,
    tenant_service,
    titular_service,
    webhook_parceiro_service,
)
from app.services.errors import NaoAutorizado

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cron", tags=["cron"])


def _exigir_segredo_cron(x_cron_secret: str | None = Header(None)) -> None:
    """Substitui o JWT de usuário aqui — quem chama é um agendador externo,
    não uma pessoa logada. `cron_secret` vazio nunca autoriza (Onda I):
    sem configurar o segredo em produção, o endpoint fica inacessível em
    vez de aberto por engano."""
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise NaoAutorizado("Segredo de cron ausente ou inválido.")


def _registrar_falha_tenant(tenant_id: str) -> None:
    """Loga e reporta ao Sentry sem propagar — usada nos dispatchers que
    iteram todos os tenants numa chamada só. Raio-X 2026-08-27: uma
    credencial quebrada de UM tenant (ex.: `ConfiguracaoWhatsApp.
    access_token` cifrado com uma chave de criptografia já rotacionada,
    virando `cryptography.fernet.InvalidToken` toda vez que lido) sem
    isolamento derrubava o dispatcher inteiro — todos os OUTROS tenants
    deixavam de ter e-mail/WhatsApp processado, e como os passos do cron
    externo (GitHub Actions) rodam em sequência, isso bloqueava também
    todo cron agendado depois deste (webhooks de parceiro, fila de
    enriquecimento, retenção de titulares etc.)."""
    logger.exception("Falha ao processar cron para o tenant %s", tenant_id)
    if settings.sentry_dsn:
        sentry_sdk.capture_exception()


@router.post("/processar-envios", dependencies=[Depends(_exigir_segredo_cron)])
def processar_envios_todos_os_tenants(
    db: Session = Depends(get_db),
    email_validation: EmailVerificationProvider = Depends(get_email_validation_provider),
) -> dict:
    """Dispatcher agendado (Onda I) — mesma lógica de `POST /envios/processar`,
    mas roda para todos os tenants numa chamada só, pensado para ser
    acionado por um cron externo (GitHub Actions) em vez de por um
    usuário autenticado."""
    resultado_por_tenant: dict[str, dict] = {}
    tenants_com_falha: list[str] = []
    totais = {"enviadas": 0, "falhas": 0, "adiadas": 0, "tarefas_linkedin_criadas": 0, "descartadas_email_invalido": 0}

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        try:
            whatsapp = resolver_whatsapp_provider(tenant.id, db)
            # E-mail resolvido por tenant, dentro do loop (raio-X
            # 2026-08-27) — igual ao WhatsApp: cada tenant manda pela
            # própria conta SMTP, sem instância única compartilhada
            # entre todos os tenants do disparo.
            email = resolver_email_provider(tenant.id, db)
            resultado = envio_service.processar_pendentes(db, tenant.id, whatsapp, email, email_validation)
        except Exception:
            db.rollback()
            _registrar_falha_tenant(tenant.id)
            tenants_com_falha.append(tenant.id)
            continue
        resultado_por_tenant[tenant.id] = resultado
        for chave in totais:
            totais[chave] += resultado[chave]

    return {"totais": totais, "por_tenant": resultado_por_tenant, "tenants_com_falha": tenants_com_falha}


@router.post("/processar-retorno", dependencies=[Depends(_exigir_segredo_cron)])
def processar_retorno_todos_os_tenants(
    db: Session = Depends(get_db),
) -> dict:
    """Dispatcher agendado das métricas de retorno (lembrete de reunião
    D-1/H-2 e disparo de pesquisa NPS pelo marco configurado) — mesmo
    padrão de `processar_envios_todos_os_tenants`. Sem isto, esses dois
    dispatchers só rodavam via chamada manual autenticada, nunca sozinhos."""
    resultado_por_tenant: dict[str, dict] = {}
    tenants_com_falha: list[str] = []
    totais = {"lembretes_d1_enviados": 0, "lembretes_h2_enviados": 0, "pesquisas_disparadas": 0}

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        try:
            whatsapp = resolver_whatsapp_provider(tenant.id, db)
            email = resolver_email_provider(tenant.id, db)
            lembretes = reuniao_service.processar_lembretes(db, tenant.id, whatsapp, email)
            nps = nps_service.disparar_pendentes(db, tenant.id, whatsapp, email)
        except Exception:
            db.rollback()
            _registrar_falha_tenant(tenant.id)
            tenants_com_falha.append(tenant.id)
            continue
        resultado_por_tenant[tenant.id] = {**lembretes, **nps}
        totais["lembretes_d1_enviados"] += lembretes["lembretes_d1_enviados"]
        totais["lembretes_h2_enviados"] += lembretes["lembretes_h2_enviados"]
        totais["pesquisas_disparadas"] += nps["pesquisas_disparadas"]

    return {"totais": totais, "por_tenant": resultado_por_tenant, "tenants_com_falha": tenants_com_falha}


@router.post("/processar-campanhas", dependencies=[Depends(_exigir_segredo_cron)])
def processar_campanhas_todos_os_tenants(
    db: Session = Depends(get_db),
) -> dict:
    """Dispatcher agendado das campanhas de e-mail/WhatsApp em massa —
    mesmo padrão síncrono/idempotente dos outros dispatchers deste
    arquivo. Diferente da cadência (LLM, cara e lenta), o envio de
    campanha é uma chamada de provider simples por destinatário, então
    processa tudo pendente de uma vez, sem lote/limite artificial."""
    resultado_por_tenant: dict[str, dict] = {}
    tenants_com_falha: list[str] = []
    totais = {"enviadas": 0, "falhas": 0}

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        try:
            whatsapp = resolver_whatsapp_provider(tenant.id, db)
            email = resolver_email_provider(tenant.id, db)
            resultado = campanha_service.processar_pendentes(db, tenant.id, email, whatsapp)
        except Exception:
            db.rollback()
            _registrar_falha_tenant(tenant.id)
            tenants_com_falha.append(tenant.id)
            continue
        resultado_por_tenant[tenant.id] = resultado
        for chave in totais:
            totais[chave] += resultado[chave]

    return {"totais": totais, "por_tenant": resultado_por_tenant, "tenants_com_falha": tenants_com_falha}


@router.post("/expirar-titulares", dependencies=[Depends(_exigir_segredo_cron)])
def expirar_titulares_todos_os_tenants(db: Session = Depends(get_db)) -> dict:
    """Retenção automática de dados de titulares (raio-X/LGPD) — mesmo
    padrão dos outros dispatchers agendados, mas 1x/dia basta (não é algo
    tempo-sensível como envio/lembrete)."""
    resultado_por_tenant: dict[str, dict] = {}
    tenants_com_falha: list[str] = []
    total_expirados = 0

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        try:
            resultado = titular_service.expirar_inativos(db, tenant.id, settings.dias_retencao_titular_inativo)
        except Exception:
            db.rollback()
            _registrar_falha_tenant(tenant.id)
            tenants_com_falha.append(tenant.id)
            continue
        resultado_por_tenant[tenant.id] = resultado
        total_expirados += resultado["decisores_expirados"]

    return {
        "total_decisores_expirados": total_expirados,
        "por_tenant": resultado_por_tenant,
        "tenants_com_falha": tenants_com_falha,
    }


@router.post("/suspender-licencas-vencidas", dependencies=[Depends(_exigir_segredo_cron)])
def suspender_licencas_vencidas(db: Session = Depends(get_db)) -> dict:
    """Suspensão automática por inadimplência (raio-X: hierarquia de
    distribuidores) — antes disto, `Licenca.data_expiracao` nunca era
    comparado com a data atual em lugar nenhum do código; uma licença
    vencida continuava dando acesso total até um humano mudar o status
    manualmente pela tela de Admin."""
    return {"tenants_suspensos": tenant_service.suspender_licencas_vencidas(db)}


@router.post("/disparar-webhooks-parceiros", dependencies=[Depends(_exigir_segredo_cron)])
def disparar_webhooks_parceiros(db: Session = Depends(get_db)) -> dict:
    """Entrega os eventos enfileirados pra Distribuidores com webhook
    configurado (Fase 2 da hierarquia, raio-X) — assinado (HMAC), com
    backoff e desistência depois de tentativas repetidas."""
    return webhook_parceiro_service.despachar_pendentes(db)


def _rodar_atualizacao_recorte_em_segundo_plano() -> None:
    """Roda fora do ciclo de vida do request (`BackgroundTasks`), com sua
    própria sessão de banco — a sessão de `Depends(get_db)` já foi fechada
    quando a tarefa em segundo plano executa, não dá pra reaproveitar."""
    db = SessionLocal()
    try:
        resultado = cnpj_recorte_service.atualizar_recorte_automatico(db)
        logger.info("Recorte de CNPJ atualizado em segundo plano: %s", resultado)
    except Exception:
        logger.exception("Falha ao atualizar recorte de CNPJ em segundo plano")
    finally:
        db.close()


@router.post("/atualizar-recorte-cnpj", dependencies=[Depends(_exigir_segredo_cron)])
def atualizar_recorte_cnpj(tarefas: BackgroundTasks) -> dict:
    """Substitui o carregamento manual do recorte de CNPJ (raio-X: usuário
    comum criando ICP não pode depender de alguém rodar um script à mão)
    — baixa da própria Receita Federal, automaticamente, só o que os ICPs
    ativos de todos os tenants ainda não têm carregado. Idempotente: rodar
    de novo sem nenhum ICP novo não baixa nada (`cnpj_recorte_service`).

    Dispara em segundo plano e responde na hora (raio-X 2026-08-26): o
    download+processamento de vários GB de CSV nacional facilmente passa
    do timeout do proxy do Render — a conexão cortava com 502 e o processo
    morria junto (não continuava em segundo plano por conta própria).
    `BackgroundTasks` roda depois da resposta ser enviada, então o timeout
    do proxy não afeta mais o processamento; o cron externo só confirma
    que foi disparado — conclusão real se vê em `RecorteCnpjEstado`."""
    tarefas.add_task(_rodar_atualizacao_recorte_em_segundo_plano)
    return {"disparado": True}


@router.post("/processar-fila-enriquecimento", dependencies=[Depends(_exigir_segredo_cron)])
def processar_fila_enriquecimento(
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    site_fetcher: SiteFetcher = Depends(get_site_fetcher),
    web_search: WebSearchProvider = Depends(get_web_search_provider),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    contact_enrichment: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider),
    graph: Neo4jClient = Depends(get_graph_client),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> dict:
    """Processa em lotes pequenos a fila de enriquecimento (site +
    decisores) de contas criadas em massa (ex.: importação de planilha de
    evento em `/icp/{icp_id}/contas/importar-participantes`) — evita
    travar o request de importação esperando LLM/busca web/Lusha por
    empresa (raio-X: planilha grande estourando timeout do proxy do
    Render, mesmo raciocínio do recorte de CNPJ)."""
    return enriquecimento_fila_service.processar_pendentes(
        db, llm, site_fetcher, web_search, account_data, contact_enrichment, graph, plan_limits
    )


@router.post("/disparar-relatorios-periodicos", dependencies=[Depends(_exigir_segredo_cron)])
def disparar_relatorios_periodicos(
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> dict:
    """Relatório periódico de volumetria/franquia/inadimplência/receita/
    churn (Fase 3 da hierarquia, raio-X) — cadência configurável por quem
    recebe (`ConfiguracaoRelatorio`), rodado 1x/dia (suficiente até pra
    cadência diária, já que checar 1x/dia é o próprio significado disso)."""
    return relatorio_service.disparar_periodicos(db, email, plan_limits)
