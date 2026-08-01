from fastapi import APIRouter

from app.api.v1.aprovacoes import router as aprovacoes_router
from app.api.v1.auditoria import router as auditoria_router
from app.api.v1.cadencias import router as cadencias_router
from app.api.v1.canais import router as canais_router
from app.api.v1.comunicacao import router as comunicacao_router
from app.api.v1.configuracao_envio import router as configuracao_envio_router
from app.api.v1.contas import router as contas_router
from app.api.v1.conversas import router as conversas_router
from app.api.v1.decisores import router as decisores_router
from app.api.v1.envios import router as envios_router
from app.api.v1.faq import router as faq_router
from app.api.v1.icp import router as icp_router
from app.api.v1.linkedin import router as linkedin_router
from app.api.v1.notificacoes import router as notificacoes_router
from app.api.v1.ofertas import router as oferta_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.optout import router as optout_router
from app.api.v1.painel import router as painel_router
from app.api.v1.qualificacao import router as qualificacao_router
from app.api.v1.reunioes import router as reunioes_router
from app.api.v1.ropa import router as ropa_router
from app.api.v1.titulares import router as titulares_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.whatsapp import router as whatsapp_router

router = APIRouter()

router.include_router(icp_router)
router.include_router(oferta_router)
router.include_router(comunicacao_router)
router.include_router(onboarding_router)
router.include_router(contas_router)
router.include_router(aprovacoes_router)
router.include_router(auditoria_router)
router.include_router(ropa_router)
router.include_router(cadencias_router)
router.include_router(envios_router)
router.include_router(whatsapp_router)
router.include_router(webhooks_router)
router.include_router(optout_router)
router.include_router(configuracao_envio_router)
router.include_router(linkedin_router)
router.include_router(canais_router)
router.include_router(qualificacao_router)
router.include_router(conversas_router)
router.include_router(notificacoes_router)
router.include_router(decisores_router)
router.include_router(reunioes_router)
router.include_router(titulares_router)
router.include_router(faq_router)
router.include_router(painel_router)
