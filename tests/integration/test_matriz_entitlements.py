"""Matriz de entitlement por plano (Fase 1, acoplamentos C1–C7).

Para cada perfil de plano (suíte e os três avulsos), cada rota da matriz
deve responder 403 exatamente quando o plano não tem nenhum dos módulos
que a rota exige. Antes da Fase 1 esta matriz falhava em C1 (MAP-only
sem painel), C3 (PREDATOR-only sem geração de lista/enriquecimento;
CRM-only com rotas de prospecção) e C4 (CRM-only sem criar conta pelo
Kanban). Os LIMITES dos planos avulsos (OI-001) não são testados aqui:
isto é acesso à rota, não franquia.
"""

import pytest

from app.api.deps import get_plan_limits_provider
from app.main import app
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT_ID = "tenant-teste"
PERIODO = "2026-09"

PERFIS = {
    "suite": set(),
    "so_map": {"predator", "crm"},
    "so_predator": {"map", "crm"},
    "so_crm": {"map", "predator"},
}

# (método, path, corpo, módulos que liberam a rota)
ROTAS = [
    ("get", "/api/v1/saude-contas/dashboard", None, {"map"}),
    ("get", "/api/v1/saude-contas/desempenho/funil", None, {"map"}),
    ("get", f"/api/v1/saude-contas/desempenho/economia?periodo={PERIODO}", None, {"map"}),
    ("get", "/api/v1/saude-contas/vendedores-com-contas", None, {"map"}),
    ("get", "/api/v1/crm/estagios", None, {"crm"}),
    ("get", f"/api/v1/crm/dashboard/economia?periodo={PERIODO}", None, {"crm"}),
    ("get", "/api/v1/icp", None, {"predator"}),
    ("get", "/api/v1/cadencias", None, {"predator"}),
    ("get", "/api/v1/contas/franquia", None, {"predator"}),
    ("get", "/api/v1/contas/limite-enriquecimento", None, {"predator"}),
    ("post", "/api/v1/contas/enriquecer-em-lote", {"conta_ids": []}, {"predator"}),
    ("get", "/api/v1/contas", None, {"crm", "predator"}),
    ("post", "/api/v1/leads/contas", {"nome": "Conta da Matriz"}, {"crm", "predator"}),
    ("get", "/api/v1/ofertas", None, {"crm", "predator"}),
    ("get", "/api/v1/nps/configuracao", None, {"map", "predator"}),
]


@pytest.mark.parametrize("perfil", PERFIS)
@pytest.mark.parametrize(("metodo", "path", "corpo", "modulos"), ROTAS, ids=[f"{m.upper()} {p}" for m, p, _, _ in ROTAS])
def test_rota_respeita_modulos_do_plano(client, monkeypatch, perfil, metodo, path, corpo, modulos):
    bloqueados = PERFIS[perfil]
    monkeypatch.setitem(
        app.dependency_overrides,
        get_plan_limits_provider,
        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT_ID: bloqueados}),
    )
    contratados = {"map", "predator", "crm"} - bloqueados

    resposta = getattr(client, metodo)(path, **({"json": corpo} if corpo is not None else {}))

    if contratados & modulos:
        assert resposta.status_code in (200, 201), (perfil, path, resposta.status_code, resposta.text)
    else:
        assert resposta.status_code == 403, (perfil, path, resposta.status_code, resposta.text)


def test_painel_do_map_devolve_o_mesmo_payload_que_o_dashboard_do_crm(client):
    """C1: a tela do MAP trocou `/crm/dashboard/*` por `/saude-contas/desempenho/*`;
    para o plano de suíte, os dados têm de ser idênticos."""
    assert (
        client.get("/api/v1/saude-contas/desempenho/funil").json()
        == client.get("/api/v1/crm/dashboard/funil").json()
    )
    assert (
        client.get(f"/api/v1/saude-contas/desempenho/economia?periodo={PERIODO}").json()
        == client.get(f"/api/v1/crm/dashboard/economia?periodo={PERIODO}").json()
    )
    assert (
        client.get("/api/v1/saude-contas/vendedores-com-contas").json()
        == client.get("/api/v1/crm/vendedores-com-contas").json()
    )
