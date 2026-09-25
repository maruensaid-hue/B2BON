"""Fitness function (Fase 17): toda rota que chama IA tem teto de uso.

Rota autenticada que recebe um `LLMProvider` precisa de
`limitar_ia_por_tenant` (teto por tenant). As exceções são os gatilhos
automáticos (webhooks, cron, links públicos), sem usuário logado: esses
passam pelo teto por hora do AI Gateway (`Gatilho.AUTOMATICO`,
`ai_limite_automatico_por_hora`).
"""

import re

from fastapi.routing import APIRoute

from app.api.deps import get_llm_provider
from app.main import app

AUTOMATICAS = re.compile(r"^/api/v1/(webhooks/|cron/|nps/responder/|auth/registrar-vitrine$)")


def _rotas(rotas):
    for rota in rotas:
        if isinstance(rota, APIRoute):
            yield rota
        elif hasattr(rota, "original_router"):
            yield from _rotas(rota.original_router.routes)
        elif hasattr(rota, "routes"):
            yield from _rotas(rota.routes)


def _dependencias(dependente):
    for sub in dependente.dependencies:
        yield sub.call
        yield from _dependencias(sub)


def test_toda_rota_com_ia_tem_limite_por_tenant_ou_e_gatilho_automatico():
    sem_limite = []
    com_ia = 0
    for rota in _rotas(app.router.routes):
        chamadas = list(_dependencias(rota.dependant))
        if get_llm_provider not in chamadas:
            continue
        com_ia += 1
        limitada = any("limitar_ia_por_tenant" in getattr(c, "__qualname__", "") for c in chamadas)
        caminho = rota.path if rota.path.startswith("/api/v1") else f"/api/v1{rota.path}"
        if not limitada and not AUTOMATICAS.search(caminho):
            sem_limite.append(f"{sorted(rota.methods)} {caminho}")
    assert com_ia >= 20
    assert sem_limite == [], sem_limite
