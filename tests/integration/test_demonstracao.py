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
                         ("get", "/api/v1/admin/tenants"), ("get", "/api/v1/comissoes/parametros"), ("get", "/api/v1/usuarios"),
                         ("get", "/api/v1/representantes"), ("get", "/api/v1/chaves-api"), ("get", "/api/v1/auditoria"),
                         ("get", "/api/v1/map/performance/equipe"), ("get", "/api/v1/finops/dashboard"),
                         ("post", "/api/v1/usuarios"), ("post", "/api/v1/ai-credits/compras"), ("post", "/api/v1/configuracao-whatsapp"),
                         ("post", "/api/v1/convites"), ("post", "/api/v1/sourcing/processos/1/descoberta"),
                         ("post", "/api/v1/auth/declarar-pagamento"), ("get", "/api/v1/rota-que-ainda-nao-existe")):
        resposta = getattr(client, metodo)(rota, headers=headers, **({"json": {}} if metodo == "post" else {}))
        assert resposta.status_code == 403 and "demonstração" in resposta.json()["detalhe"], (metodo, rota)
    # o bloqueio só vale para a sessão de demonstração
    assert client.get("/api/v1/admin/tenants").status_code == 200


def test_negacao_por_padrao_so_libera_as_telas_de_produto():
    from app.services.demo import bloqueio

    assert not bloqueio.bloqueado("GET", "/api/v1/crm/negocios") and not bloqueio.bloqueado("POST", "/api/v1/bids/licitacoes")
    assert bloqueio.bloqueado("GET", "/api/v1/crmx")  # prefixo parecido não passa
    assert bloqueio.bloqueado("POST", "/api/v1/ai-credits/compras") and not bloqueio.bloqueado("GET", "/api/v1/ai-credits/carteira")
    assert bloqueio.bloqueado("PUT", "/api/v1/planos/1") and not bloqueio.bloqueado("GET", "/api/v1/planos")
    assert bloqueio.bloqueado("POST", "/api/v1/auth/whatsapp-pessoal") and bloqueio.bloqueado("GET", "/api/v1/parceiros/contas")


def test_token_de_demonstracao_adulterado_ou_com_demo_desligada_nao_entra(client, demo, monkeypatch):
    import jwt as pyjwt

    corpo, headers = _abrir(client)
    falso = pyjwt.encode({"sub": str(corpo["usuario"]["id"]), "demo": False, "papel": "super_admin"}, "chave-errada", algorithm="HS256")
    assert client.get("/api/v1/admin/tenants", headers={"Authorization": f"Bearer {falso}"}).status_code == 401
    monkeypatch.setattr(settings, "demo_habilitada", False)  # desligar invalida as sessões abertas na hora
    assert client.get("/api/v1/crm/negocios", headers=headers).status_code == 403


def test_provedores_externos_sao_simulados_na_demonstracao(monkeypatch):
    import contextvars

    from app.api import deps
    from app.graph.nulo import GrafoNulo
    from app.providers.calendar.stub import StubCalendarProvider
    from app.providers.contact_enrichment.stub import StubContactEnrichmentProvider
    from app.providers.meeting_bot.stub import StubMeetingBotProvider
    from app.providers.payment.stub import StubPaymentProvider
    from app.providers.web_search.stub import StubWebSearchProvider
    from app.services.demo import contexto

    for chave, valor in (("sendgrid_api_key", "sg"), ("google_calendar_access_token", "g"), ("recall_api_key", "r"),
                         ("contact_enrichment_api_key", "l"), ("brave_search_api_key", "b"), ("mercadopago_access_token", "m")):
        monkeypatch.setattr(settings, chave, valor)

    def _na_demo():
        contexto.ligar()
        return (deps.get_email_provider(), deps.get_calendar_provider(), deps.get_meeting_bot_provider(),
                deps.get_contact_enrichment_provider(), deps.get_web_search_provider(), deps.get_payment_provider(),
                deps.get_graph_client(), deps.get_site_fetcher()("exemplo.com.br"))
    email, agenda, robo, lusha, busca, pagamento, grafo, site = contextvars.copy_context().run(_na_demo)
    assert isinstance(email, StubEmailProvider) and isinstance(agenda, StubCalendarProvider)
    assert isinstance(robo, StubMeetingBotProvider) and isinstance(lusha, StubContactEnrichmentProvider)
    assert isinstance(busca, StubWebSearchProvider) and isinstance(pagamento, StubPaymentProvider)
    assert isinstance(grafo, GrafoNulo) and "demonstração" in site
    assert not isinstance(deps.get_email_provider(), StubEmailProvider)  # fora da demonstração, nada muda


def test_marca_de_demonstracao_chega_ate_a_rota(client, demo):
    from app.main import app
    from app.services.demo import contexto

    app.add_api_route("/api/v1/busca/_marca_demo", lambda: {"demo": contexto.ativo()})
    try:
        _, headers = _abrir(client)
        assert client.get("/api/v1/busca/_marca_demo", headers=headers).json() == {"demo": True}
        assert client.get("/api/v1/busca/_marca_demo").json() == {"demo": False}
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/api/v1/busca/_marca_demo"]


def test_limite_por_ip_real_atras_do_proxy(client, demo, monkeypatch):
    monkeypatch.setattr(settings, "demo_max_sessoes_ativas", 100)
    from app.core import rate_limit

    for _ in range(settings.demo_sessoes_por_ip_hora):
        assert client.post("/api/v1/auth/demonstracao", headers={"X-Forwarded-For": "1.1.1.1, 200.1.1.1"}).status_code == 201
    # o primeiro IP do cabeçalho é forjável e não serve para escapar do limite
    assert client.post("/api/v1/auth/demonstracao", headers={"X-Forwarded-For": "9.9.9.9, 200.1.1.1"}).status_code == 429
    assert client.post("/api/v1/auth/demonstracao", headers={"X-Forwarded-For": "200.2.2.2"}).status_code == 201
    rate_limit.limitador_demo.resetar()


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


class _MesmaSessao:
    """Fábrica para `reabastecer` que devolve a sessão do teste (o banco em memória é um só)."""

    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    def __enter__(self):
        return self.db

    def __exit__(self, *_):
        return False


def test_reserva_abre_na_hora_e_e_reposta(client, db_session, demo, monkeypatch):
    """D-085: semear leva ~600 consultas (minutos em produção). A reserva já vem semeada; o clique só a reivindica."""
    monkeypatch.setattr(settings, "demo_reservas", 2)
    assert sessao.reabastecer(_MesmaSessao(db_session)) == {"apagadas": 0, "criadas": 2}
    reservadas = {t.id for t in db_session.query(Tenant).filter(Tenant.demo_expira_em.isnot(None))}
    assert sessao.ativas(db_session) == 0 and sessao.reservas(db_session) == 2  # reserva não ocupa vaga de sessão

    corpo, headers = _abrir(client)

    tenant_id = corpo["usuario"]["tenant_id"]
    assert tenant_id in reservadas
    assert corpo["usuario"]["email"] == sessao.semente.email_gestora(tenant_id)
    db_session.expire_all()
    expira_em = db_session.get(Tenant, tenant_id).demo_expira_em
    assert expira_em <= sessao._agora() + timedelta(hours=settings.demo_ttl_horas)  # vale 8 h a partir do clique
    assert sessao.ativas(db_session) == 1 and sessao.reservas(db_session) == 1
    assert len(client.get("/api/v1/crm/negocios", headers=headers).json()) > 0

    # Dois cliques nunca levam o mesmo ambiente; sem reserva, semeia na hora.
    segundo, _ = _abrir(client)
    terceiro, _ = _abrir(client)
    assert len({tenant_id, segundo["usuario"]["tenant_id"], terceiro["usuario"]["tenant_id"]}) == 3
    assert sessao.reabastecer(_MesmaSessao(db_session))["criadas"] == 2


def test_reserva_velha_nao_e_entregue(db_session, demo, monkeypatch):
    """As datas fictícias são relativas à semeadura: reserva perto de vencer não é mais oferecida (só expira)."""
    monkeypatch.setattr(settings, "demo_reservas", 1)
    sessao.reabastecer(_MesmaSessao(db_session))
    reserva = db_session.query(Tenant).filter(Tenant.demo_expira_em.isnot(None)).one()
    reserva.demo_expira_em = sessao._agora() + timedelta(hours=settings.demo_ttl_horas)  # dentro da folga
    db_session.commit()

    usuario, _ = sessao.criar(db_session)

    assert usuario.tenant_id != reserva.id


def test_reabastecer_desligado_ou_sem_fabrica_nao_faz_nada(db_session, monkeypatch):
    assert sessao.reabastecer(_MesmaSessao(db_session)) == {"apagadas": 0, "criadas": 0}  # demonstração desligada
    monkeypatch.setattr(settings, "demo_habilitada", True)
    assert sessao.reabastecer(None) == {"apagadas": 0, "criadas": 0}
