"""D-082: ambiente de demonstração — desligado por padrão, um tenant próprio por sessão (isolamento entre
representantes), todos os módulos preenchidos com dados fictícios, nada sai para o mundo real, nada de dados reais
entra, limite de sessões e limpeza das expiradas."""

from datetime import timedelta

import pytest

from app.api.deps import resolver_email_provider, resolver_whatsapp_provider
from app.core.config import settings
from app.models.conta import Conta
from app.models.licitacao import Licitacao
from app.models.perfil_empresa import PerfilEmpresa
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.channels.email.stub import StubEmailProvider
from app.providers.channels.whatsapp.stub import StubWhatsAppProvider
from app.services import tenant_service
from app.services.demo import sessao

ROTAS_COM_DADOS = ("/api/v1/leads/contas", "/api/v1/crm/negocios", "/api/v1/bids/licitacoes", "/api/v1/procurement/processos",
                   "/api/v1/sourcing/processos", "/api/v1/cadencias", "/api/v1/ofertas", "/api/v1/icp")


@pytest.fixture()
def demo(monkeypatch):
    monkeypatch.setattr(settings, "demo_habilitada", True)


def _abrir(client) -> tuple[dict, dict]:
    resposta = client.post("/api/v1/auth/demonstracao", headers={"Authorization": ""})
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    return corpo, {"Authorization": f"Bearer {corpo['access_token']}"}


def test_desligada_por_padrao(client):
    assert client.post("/api/v1/auth/demonstracao").status_code == 403


def test_sessao_abre_com_todos_os_modulos_preenchidos(client, db_session, demo):
    corpo, headers = _abrir(client)
    assert corpo["usuario"]["nome"] == "Marina Costa" and corpo["tem_licenca_ativa"] and corpo["demo_expira_em"]
    for rota in ROTAS_COM_DADOS:
        resposta = client.get(rota, headers=headers)
        assert resposta.status_code == 200, (rota, resposta.text[:200])
        assert len(resposta.json()) > 0, rota
    tenant_id = corpo["usuario"]["tenant_id"]
    modalidades = {lic.modalidade for lic in db_session.query(Licitacao).filter_by(tenant_id=tenant_id)}
    assert {"PUBLIC_TENDER", "PRICE_REGISTRATION", "PRIVATE_RFP", "DIRECT_AWARD"} <= modalidades  # pregão, SRP, RFP, dispensa
    assert all(u.email.endswith(".demo.invalid") and u.senha_hash is None for u in db_session.query(Usuario).filter_by(tenant_id=tenant_id))
    assert db_session.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one().visivel_no_diretorio is False
    carteira = client.get("/api/v1/ai-credits/carteira", headers=headers)
    assert carteira.status_code == 200 and carteira.json()["disponivel"] == settings.demo_creditos_ia


def test_cada_sessao_tem_seu_proprio_ambiente(client, db_session, demo):
    a, headers_a = _abrir(client)
    b, headers_b = _abrir(client)
    assert a["usuario"]["tenant_id"] != b["usuario"]["tenant_id"]
    contas_a = client.get("/api/v1/leads/contas", headers=headers_a).json()
    contas_b = client.get("/api/v1/leads/contas", headers=headers_b).json()
    assert len(contas_a) == len(contas_b) and not {c["id"] for c in contas_a} & {c["id"] for c in contas_b}
    assert client.get(f"/api/v1/crm/negocios/{client.get('/api/v1/crm/negocios', headers=headers_a).json()[0]['id']}/atividades",
                      headers=headers_b).status_code in (403, 404)  # um representante não enxerga a sessão do outro


def test_bloqueia_dados_reais_e_acoes_externas(client, demo):
    _, headers = _abrir(client)
    for metodo, rota in (("get", "/api/v1/rede-social/feed"), ("get", "/api/v1/inteligencia/oportunidades"),
                         ("get", "/api/v1/admin/tenants"), ("get", "/api/v1/comissoes/parametros"),
                         ("post", "/api/v1/usuarios"), ("post", "/api/v1/ai-credits/compras"), ("post", "/api/v1/configuracao-whatsapp"),
                         ("post", "/api/v1/convites"), ("post", "/api/v1/sourcing/processos/1/descoberta")):
        resposta = getattr(client, metodo)(rota, headers=headers, **({"json": {}} if metodo == "post" else {}))
        assert resposta.status_code == 403 and "demonstração" in resposta.json()["detalhe"], (metodo, rota)
    # o bloqueio só vale para a sessão de demonstração
    assert client.get("/api/v1/admin/tenants").status_code == 200


def test_envios_da_demonstracao_sao_simulados(client, db_session, demo, monkeypatch):
    corpo, _ = _abrir(client)
    monkeypatch.setattr(type(settings), "e_ambiente_producao", property(lambda self: True))
    tenant_id = corpo["usuario"]["tenant_id"]
    assert isinstance(resolver_email_provider(tenant_id, db_session), StubEmailProvider)
    assert isinstance(resolver_whatsapp_provider(tenant_id, db_session), StubWhatsAppProvider)


def test_limite_de_sessoes_e_limpeza_das_expiradas(client, db_session, demo, monkeypatch):
    corpo, headers = _abrir(client)
    monkeypatch.setattr(settings, "demo_max_sessoes_ativas", 1)
    assert client.post("/api/v1/auth/demonstracao").status_code == 409  # teto de sessões ativas
    tenant_id = corpo["usuario"]["tenant_id"]
    assert tenant_id not in {t.id for t in tenant_service.listar_tenants(db_session)}  # fora das visões da plataforma
    tenant = db_session.get(Tenant, tenant_id)
    tenant.demo_expira_em = tenant.demo_expira_em - timedelta(hours=settings.demo_ttl_horas + 1)
    db_session.commit()
    assert sessao.purgar_expiradas(db_session) == 1
    db_session.expire_all()
    assert db_session.get(Tenant, tenant_id) is None and db_session.query(Conta).filter_by(tenant_id=tenant_id).count() == 0
    assert client.get("/api/v1/leads/contas", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/demonstracao").status_code == 201  # vaga liberada


def test_paineis_e_areas_de_trabalho_abrem_com_os_dados_da_demonstracao(client, demo):
    _, headers = _abrir(client)
    licitacao = client.get("/api/v1/bids/licitacoes", headers=headers).json()[0]["id"]
    processo = client.get("/api/v1/procurement/processos", headers=headers).json()[0]["id"]
    rfp = next(p for p in client.get("/api/v1/sourcing/processos", headers=headers).json() if p["tipo_processo"] == "RFP")["id"]
    negocio = client.get("/api/v1/crm/negocios", headers=headers).json()[0]["id"]
    rotas = ("/api/v1/painel/metrica-norte", "/api/v1/crm/dashboard/funil", "/api/v1/crm/dashboard/atividade", "/api/v1/crm/estagios",
             f"/api/v1/crm/negocios/{negocio}/atividades", f"/api/v1/crm/negocios/{negocio}/propostas",
             "/api/v1/saude-contas/dashboard", "/api/v1/saude-contas/ranking", "/api/v1/reunioes", "/api/v1/aprovacoes",
             "/api/v1/campanhas", "/api/v1/listas-prospeccao", "/api/v1/nps/configuracao",
             f"/api/v1/bids/licitacoes/{licitacao}/workspace", f"/api/v1/bids/licitacoes/{licitacao}/matriz",
             f"/api/v1/procurement/processos/{processo}/workspace", "/api/v1/procurement/metricas", "/api/v1/procurement/fornecedores",
             "/api/v1/procurement/contratos", f"/api/v1/sourcing/processos/{rfp}/workspace", f"/api/v1/sourcing/processos/{rfp}/comparacao",
             "/api/v1/ai-credits/carteira", "/api/v1/busca?q=Horizonte")
    falhas = {r: client.get(r, headers=headers).status_code for r in rotas}
    assert {r: s for r, s in falhas.items() if s >= 400} == {}
