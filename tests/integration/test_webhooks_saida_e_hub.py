"""Webhooks de saída (eventos de domínio) e Integration Hub (Fase 3)."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.integrations import registry, sync
from app.contexts.integrations.contract import AdapterCapabilities, Page
from app.contexts.platform import webhooks
from app.contexts.shared import events
from app.contexts.shared.canonical.base import DataClassification, SourceRef
from app.contexts.shared.canonical.commercial import Account, AccountLifecycle
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.entrega_webhook import EntregaWebhook
from app.models.execucao_sync import ExecucaoSync

TENANT_ID = "tenant-teste"
SEGREDO_CRON = "segredo-cron-teste"


@pytest.fixture(autouse=True)
def _cron(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", SEGREDO_CRON)
    events.cancelar_inscricoes()
    yield
    events.cancelar_inscricoes()


@pytest.fixture()
def envios(monkeypatch):
    registro = {"respostas": [], "chamadas": []}

    def enviar(url, corpo, cabecalhos):
        registro["chamadas"].append((url, corpo, cabecalhos))
        return registro["respostas"].pop(0) if registro["respostas"] else 200

    monkeypatch.setattr(webhooks, "_enviar_httpx", enviar)
    return registro


def _criar_negocio(client, db):
    conta = Conta(tenant_id=TENANT_ID, nome="C", status="prospectada")
    db.add(conta)
    db.commit()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="D")
    db.add(decisor)
    db.commit()
    return client.post("/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "N", "valor": 10}).json()


def _cron_eventos(client):
    resposta = client.post("/api/v1/cron/processar-eventos", headers={"X-Cron-Secret": SEGREDO_CRON})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_evento_de_negocio_chega_assinado_ao_webhook(client, db_session, envios):
    criado = client.post("/api/v1/webhooks-saida", json={"url": "https://cliente.exemplo/hook", "eventos": ["OpportunityCreated"]}).json()
    segredo = criado["segredo"]
    negocio = _criar_negocio(client, db_session)

    resultado = _cron_eventos(client)

    assert resultado["webhooks"]["entregues"] == 1
    url, corpo, cabecalhos = envios["chamadas"][0]
    assert url == "https://cliente.exemplo/hook"
    payload = json.loads(corpo)
    assert payload["type"] == "OpportunityCreated" and payload["aggregate"]["id"] == str(negocio["id"])
    t, v1 = (parte.split("=", 1)[1] for parte in cabecalhos["X-B2BON-Signature"].split(","))
    esperado = hmac.new(segredo.encode(), f"{t}.".encode() + corpo, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(v1, esperado)


def test_reprocessar_nao_duplica_entrega(client, db_session, envios):
    client.post("/api/v1/webhooks-saida", json={"url": "https://c.exemplo/h", "eventos": ["OpportunityCreated"]})
    _criar_negocio(client, db_session)
    _cron_eventos(client)
    _cron_eventos(client)
    assert len(envios["chamadas"]) == 1
    assert db_session.query(EntregaWebhook).count() == 1


def test_evento_confidencial_nunca_sai_por_webhook(client, db_session, envios):
    client.post("/api/v1/webhooks-saida", json={"url": "https://c.exemplo/h", "eventos": ["ProcurementDemandCreated"]})
    events.publicar(
        db_session, events.TipoEvento.PROCUREMENT_DEMAND_CREATED, TENANT_ID, "demanda", 1, {"orcamento": 999},
        classificacao=DataClassification.CONFIDENTIAL,
    )
    db_session.commit()
    _cron_eventos(client)
    assert envios["chamadas"] == [] and db_session.query(EntregaWebhook).count() == 0


def test_evento_de_outro_tenant_nao_vai_para_o_webhook_deste(client, db_session, envios):
    client.post("/api/v1/webhooks-saida", json={"url": "https://c.exemplo/h", "eventos": ["OpportunityCreated"]})
    events.publicar(db_session, events.TipoEvento.OPPORTUNITY_CREATED, "tenant-outro", "negocio", 99)
    db_session.commit()
    _cron_eventos(client)
    assert envios["chamadas"] == []


def test_falha_reagenda_com_backoff_e_desiste_no_limite(client, db_session, envios):
    client.post("/api/v1/webhooks-saida", json={"url": "https://c.exemplo/h", "eventos": ["OpportunityCreated"]})
    _criar_negocio(client, db_session)
    webhooks.garantir_inscricao()
    events.processar_pendentes(db_session)
    envios["respostas"] = [500] * webhooks.MAX_TENTATIVAS

    agora = datetime.now(UTC)
    primeira = webhooks.despachar_entregas(db_session, agora=agora)
    entrega = db_session.query(EntregaWebhook).one()
    assert primeira["reagendadas"] == 1 and entrega.status == "pendente" and entrega.ultimo_status_http == 500
    assert webhooks.despachar_entregas(db_session, agora=agora)["reagendadas"] == 0  # ainda não venceu

    for _ in range(webhooks.MAX_TENTATIVAS):
        agora += timedelta(hours=7)
        webhooks.despachar_entregas(db_session, agora=agora)
    db_session.refresh(entrega)
    assert entrega.status == "desistida" and entrega.tentativas == webhooks.MAX_TENTATIVAS


def test_evento_invalido_ou_url_invalida_sao_rejeitados(client):
    assert client.post("/api/v1/webhooks-saida", json={"url": "https://c.exemplo/h", "eventos": ["Inventado"]}).status_code == 422
    assert client.post("/api/v1/webhooks-saida", json={"url": "ftp://c", "eventos": ["OpportunityCreated"]}).status_code == 422


def test_segredo_do_webhook_fica_criptografado_em_repouso(client, db_session):
    segredo = client.post("/api/v1/webhooks-saida", json={"url": "https://c.exemplo/h", "eventos": ["OpportunityCreated"]}).json()["segredo"]
    bruto = db_session.execute(__import__("sqlalchemy").text("select segredo from assinatura_webhook_tenant")).scalar()
    assert bruto != segredo and segredo not in bruto


# --- Integration Hub ------------------------------------------------------------------------
def test_conectores_futuros_aparecem_como_coming_soon_e_nao_conectam(client):
    conectores = {c["sistema"]: c["status"] for c in client.get("/api/v1/hub-integracoes/conectores").json()}
    assert conectores["b2bon_crm"] == "AVAILABLE"
    assert {conectores[s] for s in ("salesforce", "hubspot", "pipedrive", "rd_station")} == {"COMING_SOON"}
    assert client.post("/api/v1/hub-integracoes/conexoes", json={"sistema": "hubspot", "nome": "x"}).status_code == 422


def test_sync_do_crm_interno_registra_execucao_e_depois_e_incremental(client, db_session):
    for i in range(3):
        db_session.add(Conta(tenant_id=TENANT_ID, nome=f"C{i}", status="prospectada"))
    db_session.commit()
    conexao = client.post("/api/v1/hub-integracoes/conexoes", json={"sistema": "b2bon_crm", "nome": "Próprio"}).json()
    assert "credenciais" not in conexao

    primeira = client.post(f"/api/v1/hub-integracoes/conexoes/{conexao['id']}/sincronizar/accounts").json()
    segunda = client.post(f"/api/v1/hub-integracoes/conexoes/{conexao['id']}/sincronizar/accounts").json()

    assert primeira["status"] == "sucesso" and primeira["itens_lidos"] == 3
    execucoes = db_session.query(ExecucaoSync).order_by(ExecucaoSync.id).all()
    assert execucoes[0].incremental_desde is None and execucoes[1].incremental_desde is not None
    assert segunda["status"] == "sucesso"


def test_conexao_de_outro_tenant_nao_e_acessivel(client, criar_usuario_autenticado):
    conexao = client.post("/api/v1/hub-integracoes/conexoes", json={"sistema": "b2bon_crm", "nome": "A"}).json()
    headers_b = criar_usuario_autenticado("tenant-b-hub", papel="admin", email="a@b-hub.com")
    assert client.post(f"/api/v1/hub-integracoes/conexoes/{conexao['id']}/sincronizar/accounts", headers=headers_b).status_code == 404
    assert client.get("/api/v1/hub-integracoes/conexoes", headers=headers_b).json() == []


class _AdapterInstavel:
    """Falha transitoriamente nas primeiras chamadas, depois pagina."""

    def __init__(self, falhas: int):
        self.falhas = falhas

    def capabilities(self):
        return AdapterCapabilities(system="instavel", readable_entities=frozenset({"Account"}), incremental_sync=True)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100):
        if self.falhas:
            self.falhas -= 1
            raise sync.ErroTransitorio("429")
        conta = Account(id=f"instavel:account:{cursor or 0}", tenant_id=tenant_id, source=SourceRef(system="instavel", external_id="1", entity="a"), organization_id="o", lifecycle=AccountLifecycle.PROSPECT)
        return Page(items=[conta], next_cursor=None if cursor else "1")


def test_sync_faz_retry_em_erro_transitorio_e_registra_tentativas(db_session):
    adapter = _AdapterInstavel(falhas=2)
    registry.registrar(registry.Conector(sistema="instavel", nome="Instável", status=registry.StatusConector.BETA, auth=registry.TipoAuth.NENHUMA, descricao="teste"), lambda db, c: adapter)
    try:
        conexao = ConexaoIntegracao(tenant_id=TENANT_ID, sistema="instavel", nome="x", status="ativa", configuracao={})
        db_session.add(conexao)
        db_session.commit()
        recebidos = []
        execucao = sync.sincronizar(db_session, conexao, "accounts", destino=recebidos.extend, dormir=lambda s: None)
        assert execucao.status == "sucesso" and execucao.paginas == 2 and execucao.itens_lidos == 2
        assert execucao.tentativas == 4  # 3 na 1ª página (2 falhas + sucesso) + 1 na 2ª
        assert len(recebidos) == 2
    finally:
        registry.remover("instavel")


def test_sync_registra_falha_sem_derrubar(db_session):
    adapter = _AdapterInstavel(falhas=99)
    registry.registrar(registry.Conector(sistema="instavel", nome="Instável", status=registry.StatusConector.BETA, auth=registry.TipoAuth.NENHUMA, descricao="teste"), lambda db, c: adapter)
    try:
        conexao = ConexaoIntegracao(tenant_id=TENANT_ID, sistema="instavel", nome="x", status="ativa", configuracao={})
        db_session.add(conexao)
        db_session.commit()
        execucao = sync.sincronizar(db_session, conexao, "accounts", dormir=lambda s: None)
        assert execucao.status == "falha" and "429" in execucao.erro
        assert conexao.ultimo_erro == execucao.erro
    finally:
        registry.remover("instavel")
