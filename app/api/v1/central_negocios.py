from fastapi import APIRouter, Depends

from app.api.deps import get_mercado_client, get_noticias_client
from app.integrations.central_negocios_client import MercadoClient, NoticiasClient
from app.schemas.central_negocios import MercadoSchema, NoticiaSchema
from app.services import central_negocios_service

router = APIRouter(prefix="/central-negocios", tags=["central-negocios"])


@router.get("/mercado", response_model=MercadoSchema)
def obter_mercado(mercado_client: MercadoClient = Depends(get_mercado_client)) -> MercadoSchema:
    """B3 (Ibovespa) + câmbio — página pública, sem autenticação (Central
    de Negócios, raio-X 2026-09-21). Cacheado por 15min em `central_negocios_service`."""
    return central_negocios_service.obter_mercado(mercado_client)


@router.get("/noticias", response_model=list[NoticiaSchema])
def obter_noticias(noticias_client: NoticiasClient = Depends(get_noticias_client)) -> list[NoticiaSchema]:
    """Últimas matérias reais dos RSS de negócios (UOL/G1/InfoMoney) —
    mesma página pública, mesmo cache de 15min."""
    return central_negocios_service.obter_noticias(noticias_client)
