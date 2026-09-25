"""Catálogo comercial e assinatura do tenant (Fase 14).

`GET /catalogo` é público (página de planos): produtos, estado de cada um
e o comparativo dos planos self-service com preços da tabela `plano`.
`GET /assinatura` é do tenant logado e não exige licença ativa: quem está
suspenso também precisa ver o próprio plano e o uso.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_plan_limits_provider, get_usuario_atual
from app.contexts.platform.contract import catalogo
from app.models.usuario import Usuario
from app.providers.plan_limits.base import PlanLimitsProvider

router = APIRouter(tags=["catalogo"])


@router.get("/catalogo")
def ver_catalogo(response: Response, db: Session = Depends(get_db)) -> dict:
    # Público e igual para todos: cache curto no navegador/CDN (Fase 17).
    response.headers["Cache-Control"] = "public, max-age=300"
    return catalogo.catalogo(db)


@router.get("/assinatura")
def minha_assinatura(
    usuario: Usuario = Depends(get_usuario_atual),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
    db: Session = Depends(get_db),
) -> dict:
    return catalogo.assinatura(db, usuario.tenant_id, plan_limits)
