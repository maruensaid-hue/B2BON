from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_email_provider, get_email_validation_provider, resolver_whatsapp_provider
from app.core.config import settings
from app.models.tenant import Tenant
from app.providers.channels.email.base import EmailProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.services import campanha_service, envio_service, nps_service, reuniao_service, tenant_service, titular_service
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

    for tenant in db.query(Tenant).order_by(Tenant.id).all():
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

    for tenant in db.query(Tenant).order_by(Tenant.id).all():
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

    for tenant in db.query(Tenant).order_by(Tenant.id).all():
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

    for tenant in db.query(Tenant).order_by(Tenant.id).all():
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
