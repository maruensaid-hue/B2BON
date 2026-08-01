from fastapi import APIRouter

from app.api.v1.aprovacoes import router as aprovacoes_router
from app.api.v1.auditoria import router as auditoria_router
from app.api.v1.comunicacao import router as comunicacao_router
from app.api.v1.contas import router as contas_router
from app.api.v1.icp import router as icp_router
from app.api.v1.ofertas import router as oferta_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.ropa import router as ropa_router

router = APIRouter()

router.include_router(icp_router)
router.include_router(oferta_router)
router.include_router(comunicacao_router)
router.include_router(onboarding_router)
router.include_router(contas_router)
router.include_router(aprovacoes_router)
router.include_router(auditoria_router)
router.include_router(ropa_router)

# Routers por épico (E3-Cadências...) serão incluídos aqui conforme a lógica
# de negócio for implementada (Onda 2 em diante).
