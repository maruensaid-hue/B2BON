from fastapi import APIRouter, Depends

from app.api.deps import exigir_licenca_ativa
from app.api.v1.admin_tenants import router as admin_tenants_router
from app.api.v1.aprovacoes import router as aprovacoes_router
from app.api.v1.auditoria import router as auditoria_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cadencias import router as cadencias_router
from app.api.v1.campanhas import router as campanhas_router
from app.api.v1.canais import router as canais_router
from app.api.v1.comunicacao import router as comunicacao_router
from app.api.v1.configuracao_envio import router as configuracao_envio_router
from app.api.v1.configuracao_whatsapp import router as configuracao_whatsapp_router
from app.api.v1.contas import router as contas_router
from app.api.v1.convites import router as convites_router
from app.api.v1.crm import router as crm_router
from app.api.v1.conversas import router as conversas_router
from app.api.v1.cron import router as cron_router
from app.api.v1.decisores import router as decisores_router
from app.api.v1.envios import router as envios_router
from app.api.v1.faq import router as faq_router
from app.api.v1.icp import router as icp_router
from app.api.v1.indicacoes import router as indicacoes_router
from app.api.v1.integracoes import router as integracoes_router
from app.api.v1.leads import router as leads_router
from app.api.v1.linkedin import router as linkedin_router
from app.api.v1.motor import router as motor_router
from app.api.v1.notificacoes import router as notificacoes_router
from app.api.v1.nps import router as nps_router
from app.api.v1.ofertas import router as oferta_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.optout import router as optout_router
from app.api.v1.painel import router as painel_router
from app.api.v1.parceiros import router as parceiros_router
from app.api.v1.planos import router as planos_router
from app.api.v1.relatorios import router as relatorios_router
from app.api.v1.qualificacao import router as qualificacao_router
from app.api.v1.rede_social import router as rede_social_router
from app.api.v1.reunioes import router as reunioes_router
from app.api.v1.ropa import router as ropa_router
from app.api.v1.saude_conta import router as saude_conta_router
from app.api.v1.template_proposta import router as template_proposta_router
from app.api.v1.titulares import router as titulares_router
from app.api.v1.usuarios import router as usuarios_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.whatsapp import router as whatsapp_router

router = APIRouter()

# Módulos pagos (PREDATOR/CRM/MAP) — travados para tenants sem licença
# ativa (Onda H: convite-vitrine só dá acesso à Rede Social). Auth,
# convites, planos, admin de tenant, webhooks/optout/cron (públicos,
# com seu próprio mecanismo de autenticação) e a própria Rede Social
# ficam de fora deliberadamente.
_exige_licenca = [Depends(exigir_licenca_ativa)]

router.include_router(icp_router, dependencies=_exige_licenca)
router.include_router(oferta_router, dependencies=_exige_licenca)
router.include_router(comunicacao_router, dependencies=_exige_licenca)
router.include_router(onboarding_router, dependencies=_exige_licenca)
router.include_router(contas_router, dependencies=_exige_licenca)
router.include_router(aprovacoes_router, dependencies=_exige_licenca)
router.include_router(auditoria_router)
router.include_router(ropa_router, dependencies=_exige_licenca)
router.include_router(cadencias_router, dependencies=_exige_licenca)
router.include_router(campanhas_router, dependencies=_exige_licenca)
router.include_router(envios_router, dependencies=_exige_licenca)
router.include_router(whatsapp_router, dependencies=_exige_licenca)
router.include_router(webhooks_router)
router.include_router(optout_router)
router.include_router(cron_router)
router.include_router(configuracao_envio_router, dependencies=_exige_licenca)
router.include_router(configuracao_whatsapp_router, dependencies=_exige_licenca)
router.include_router(linkedin_router, dependencies=_exige_licenca)
router.include_router(canais_router, dependencies=_exige_licenca)
router.include_router(qualificacao_router, dependencies=_exige_licenca)
router.include_router(conversas_router, dependencies=_exige_licenca)
router.include_router(notificacoes_router, dependencies=_exige_licenca)
router.include_router(decisores_router, dependencies=_exige_licenca)
router.include_router(reunioes_router, dependencies=_exige_licenca)
router.include_router(titulares_router, dependencies=_exige_licenca)
router.include_router(faq_router, dependencies=_exige_licenca)
router.include_router(painel_router, dependencies=_exige_licenca)
router.include_router(nps_router, dependencies=_exige_licenca)
router.include_router(indicacoes_router, dependencies=_exige_licenca)
router.include_router(leads_router, dependencies=_exige_licenca)
router.include_router(auth_router)
router.include_router(convites_router)
router.include_router(planos_router)
router.include_router(admin_tenants_router)
# Fase 2 da hierarquia (raio-X): /integracoes é JWT (Distribuidor logado
# gerenciando chave/webhook próprios), /parceiros é chave de API (sistema
# do Distribuidor chamando de fora) — nenhum dos dois passa por
# exigir_licenca_ativa, mesmo raciocínio de /admin/tenants (administrativo,
# não módulo pago do PREDATOR).
router.include_router(integracoes_router)
router.include_router(parceiros_router)
router.include_router(relatorios_router)
router.include_router(crm_router, dependencies=_exige_licenca)
router.include_router(rede_social_router)
router.include_router(motor_router, dependencies=_exige_licenca)
# MAP de contas — visível a user/admin/super_admin dentro do próprio
# tenant (escopo aplicado no serviço), distinto do /motor acima (só
# super_admin, cross-tenant).
router.include_router(saude_conta_router, dependencies=_exige_licenca)
router.include_router(usuarios_router, dependencies=_exige_licenca)
router.include_router(template_proposta_router, dependencies=_exige_licenca)
