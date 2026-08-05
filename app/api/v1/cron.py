from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_email_provider, get_email_validation_provider, get_whatsapp_provider
from app.core.config import settings
from app.models.tenant import Tenant
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.email_validation.base import EmailVerificationProvider
from app.services import envio_service
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
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
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
        resultado = envio_service.processar_pendentes(db, tenant.id, whatsapp, email, email_validation)
        resultado_por_tenant[tenant.id] = resultado
        for chave in totais:
            totais[chave] += resultado[chave]

    return {"totais": totais, "por_tenant": resultado_por_tenant}
