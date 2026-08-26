from fastapi import APIRouter, Depends, Header
from sqlalchemy import inspect as sa_inspect, text
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
    resolver_whatsapp_provider,
)
from app.core.config import settings
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

router = APIRouter(prefix="/cron", tags=["cron"])


def _exigir_segredo_cron(x_cron_secret: str | None = Header(None)) -> None:
    """Substitui o JWT de usuário aqui — quem chama é um agendador externo,
    não uma pessoa logada. `cron_secret` vazio nunca autoriza (Onda I):
    sem configurar o segredo em produção, o endpoint fica inacessível em
    vez de aberto por engano."""
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise NaoAutorizado("Segredo de cron ausente ou inválido.")


@router.post("/processar-envios", dependencies=[Depends(_exigir_segredo_cron)])
def processar_envios_todos_os_tenants(
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
    email_validation: EmailVerificationProvider = Depends(get_email_validation_provider),
) -> dict:
    """Dispatcher agendado (Onda I) — mesma lógica de `POST /envios/processar`,
    mas roda para todos os tenants numa chamada só, pensado para ser
    acionado por um cron externo (GitHub Actions) em vez de por um
    usuário autenticado."""
    resultado_por_tenant: dict[str, dict] = {}
    totais = {"enviadas": 0, "falhas": 0, "adiadas": 0, "tarefas_linkedin_criadas": 0, "descartadas_email_invalido": 0}

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        whatsapp = resolver_whatsapp_provider(tenant.id, db)
        resultado = envio_service.processar_pendentes(db, tenant.id, whatsapp, email, email_validation)
        resultado_por_tenant[tenant.id] = resultado
        for chave in totais:
            totais[chave] += resultado[chave]

    return {"totais": totais, "por_tenant": resultado_por_tenant}


@router.post("/processar-retorno", dependencies=[Depends(_exigir_segredo_cron)])
def processar_retorno_todos_os_tenants(
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> dict:
    """Dispatcher agendado das métricas de retorno (lembrete de reunião
    D-1/H-2 e disparo de pesquisa NPS pelo marco configurado) — mesmo
    padrão de `processar_envios_todos_os_tenants`. Sem isto, esses dois
    dispatchers só rodavam via chamada manual autenticada, nunca sozinhos."""
    resultado_por_tenant: dict[str, dict] = {}
    totais = {"lembretes_d1_enviados": 0, "lembretes_h2_enviados": 0, "pesquisas_disparadas": 0}

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        whatsapp = resolver_whatsapp_provider(tenant.id, db)
        lembretes = reuniao_service.processar_lembretes(db, tenant.id, whatsapp, email)
        nps = nps_service.disparar_pendentes(db, tenant.id, whatsapp, email)
        resultado_por_tenant[tenant.id] = {**lembretes, **nps}
        totais["lembretes_d1_enviados"] += lembretes["lembretes_d1_enviados"]
        totais["lembretes_h2_enviados"] += lembretes["lembretes_h2_enviados"]
        totais["pesquisas_disparadas"] += nps["pesquisas_disparadas"]

    return {"totais": totais, "por_tenant": resultado_por_tenant}


@router.post("/processar-campanhas", dependencies=[Depends(_exigir_segredo_cron)])
def processar_campanhas_todos_os_tenants(
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> dict:
    """Dispatcher agendado das campanhas de e-mail/WhatsApp em massa —
    mesmo padrão síncrono/idempotente dos outros dispatchers deste
    arquivo. Diferente da cadência (LLM, cara e lenta), o envio de
    campanha é uma chamada de provider simples por destinatário, então
    processa tudo pendente de uma vez, sem lote/limite artificial."""
    resultado_por_tenant: dict[str, dict] = {}
    totais = {"enviadas": 0, "falhas": 0}

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        whatsapp = resolver_whatsapp_provider(tenant.id, db)
        resultado = campanha_service.processar_pendentes(db, tenant.id, email, whatsapp)
        resultado_por_tenant[tenant.id] = resultado
        for chave in totais:
            totais[chave] += resultado[chave]

    return {"totais": totais, "por_tenant": resultado_por_tenant}


@router.post("/expirar-titulares", dependencies=[Depends(_exigir_segredo_cron)])
def expirar_titulares_todos_os_tenants(db: Session = Depends(get_db)) -> dict:
    """Retenção automática de dados de titulares (raio-X/LGPD) — mesmo
    padrão dos outros dispatchers agendados, mas 1x/dia basta (não é algo
    tempo-sensível como envio/lembrete)."""
    resultado_por_tenant: dict[str, dict] = {}
    total_expirados = 0

    for tenant in db.query(Tenant).filter_by(ativo=True).order_by(Tenant.id).all():
        resultado = titular_service.expirar_inativos(db, tenant.id, settings.dias_retencao_titular_inativo)
        resultado_por_tenant[tenant.id] = resultado
        total_expirados += resultado["decisores_expirados"]

    return {"total_decisores_expirados": total_expirados, "por_tenant": resultado_por_tenant}


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


@router.post("/atualizar-recorte-cnpj", dependencies=[Depends(_exigir_segredo_cron)])
def atualizar_recorte_cnpj(db: Session = Depends(get_db)) -> dict:
    """Substitui o carregamento manual do recorte de CNPJ (raio-X: usuário
    comum criando ICP não pode depender de alguém rodar um script à mão)
    — baixa da própria Receita Federal, automaticamente, só o que os ICPs
    ativos de todos os tenants ainda não têm carregado. Idempotente: rodar
    de novo sem nenhum ICP novo não baixa nada (`cnpj_recorte_service`)."""
    return cnpj_recorte_service.atualizar_recorte_automatico(db)


@router.post("/processar-fila-enriquecimento", dependencies=[Depends(_exigir_segredo_cron)])
def processar_fila_enriquecimento(
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    site_fetcher: SiteFetcher = Depends(get_site_fetcher),
    web_search: WebSearchProvider = Depends(get_web_search_provider),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    contact_enrichment: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> dict:
    """Processa em lotes pequenos a fila de enriquecimento (site +
    decisores) de contas criadas em massa (ex.: importação de planilha de
    evento em `/icp/{icp_id}/contas/importar-participantes`) — evita
    travar o request de importação esperando LLM/busca web/Lusha por
    empresa (raio-X: planilha grande estourando timeout do proxy do
    Render, mesmo raciocínio do recorte de CNPJ)."""
    return enriquecimento_fila_service.processar_pendentes(
        db, llm, site_fetcher, web_search, account_data, contact_enrichment, graph
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


# --- Diagnóstico/reparo temporário (raio-X 2026-08-26) ---
# `recorte_cnpj_estado` (e possivelmente outras tabelas) existe na migração
# do Alembic mas não existia no banco de produção, mesmo com o deploy
# rodando `alembic upgrade head` a cada subida — sinal de que
# `alembic_version` em produção está "adiantado" (ou o `create_all`
# nunca rodou de verdade) em relação ao schema real. Sem Shell disponível
# no plano do Render pra investigar direto, essas duas rotas existem só
# pra diagnosticar e destravar produção às pressas; REMOVER depois que o
# desalinhamento for confirmado e corrigido.


@router.get("/diagnostico-schema", dependencies=[Depends(_exigir_segredo_cron)])
def diagnostico_schema(db: Session = Depends(get_db)) -> dict:
    versao = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    tabelas_checar = [
        "conta", "convite_vitrine", "recorte_cnpj_estado", "lista_prospeccao",
        "fila_enriquecimento_conta", "tenant",
    ]
    tabelas = {
        nome: db.execute(text("SELECT to_regclass(:nome)"), {"nome": nome}).scalar() is not None
        for nome in tabelas_checar
    }
    coluna_tenant_ativo = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'tenant' AND column_name = 'ativo'"
        )
    ).scalar()
    return {
        "alembic_version": versao,
        "tabelas_existem": tabelas,
        "tenant_tem_coluna_ativo": coluna_tenant_ativo is not None,
    }


@router.post("/reparar-schema", dependencies=[Depends(_exigir_segredo_cron)])
def reparar_schema(db: Session = Depends(get_db)) -> dict:
    """`create_all` só cria tabelas que faltam — nunca altera/apaga o que
    já existe. Destrava produção sem esperar a investigação completa da
    causa raiz do `alembic_version` desalinhado."""
    from app.db.base import Base

    engine = db.get_bind()
    antes = set(sa_inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine)
    depois = set(sa_inspect(engine).get_table_names())
    return {"tabelas_criadas": sorted(depois - antes)}
