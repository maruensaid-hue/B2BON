"""Webhooks públicos falham fechados (V5.2.1): nenhum efeito colateral sem segredo/assinatura válidos.

Antes da correção, `/webhooks/whatsapp`, `/webhooks/email` e `/webhooks/reputacao` aceitavam `tenant_id` do corpo sem autenticação, e
`/webhooks/whatsapp/meta` não verificava a assinatura da Meta."""

import hashlib
import hmac
import json

import pytest

from app.core.config import settings
from app.models.decisor import Decisor
from app.models.pausa_canal import PausaCanal
from app.models.registro_reputacao_canal import RegistroReputacaoCanal
from tests.conftest import APP_SECRET_META_TESTE

TENANT_ID = "tenant-teste"
CORPO_REPUTACAO = {"tenant_id": TENANT_ID, "canal": "email", "tipo_evento": "bounce", "quantidade": 500}
CORPO_WHATSAPP = {"tenant_id": TENANT_ID, "telefone": "+5511999990000", "texto": "SAIR"}
CORPO_EMAIL = {"tenant_id": TENANT_ID, "email": "alguem@exemplo.com", "texto": "pare de me escrever"}
ROTAS_INTERNAS = [
    ("/api/v1/webhooks/reputacao", CORPO_REPUTACAO),
    ("/api/v1/webhooks/whatsapp", CORPO_WHATSAPP),
    ("/api/v1/webhooks/email", CORPO_EMAIL),
]


@pytest.mark.parametrize(("rota", "corpo"), ROTAS_INTERNAS)
def test_webhook_interno_sem_segredo_ou_com_segredo_errado_e_recusado(client, rota, corpo):
    assert client.post(rota, json=corpo, headers={"X-Webhook-Secret": "errado"}).status_code == 403
    sem_cabecalho = {k: v for k, v in client.headers.items() if k.lower() != "x-webhook-secret"}
    assert client.post(rota, json=corpo, headers={**sem_cabecalho, "X-Webhook-Secret": ""}).status_code == 403


@pytest.mark.parametrize(("rota", "corpo"), ROTAS_INTERNAS)
def test_webhook_interno_sem_segredo_configurado_nunca_autoriza(client, monkeypatch, rota, corpo):
    monkeypatch.setattr(settings, "webhook_interno_secret", "")
    assert client.post(rota, json=corpo, headers={"X-Webhook-Secret": ""}).status_code == 403
    assert client.post(rota, json=corpo, headers={"X-Webhook-Secret": "qualquer"}).status_code == 403


def test_reputacao_forjada_nao_registra_evento_nem_pausa_o_canal_do_tenant(client, db_session):
    resposta = client.post("/api/v1/webhooks/reputacao", json=CORPO_REPUTACAO, headers={"X-Webhook-Secret": "errado"})

    assert resposta.status_code == 403
    assert db_session.query(RegistroReputacaoCanal).count() == 0
    assert db_session.query(PausaCanal).count() == 0


def test_optout_forjado_nao_suprime_o_decisor(client, db_session, onboarding_completo, criar_conta_com_decisor):
    _, decisor = criar_conta_com_decisor()

    resposta = client.post(
        "/api/v1/webhooks/whatsapp",
        json={"tenant_id": TENANT_ID, "telefone": decisor.telefone, "texto": "SAIR"},
        headers={"X-Webhook-Secret": "errado"},
    )

    assert resposta.status_code == 403
    db_session.expire_all()
    assert db_session.get(Decisor, decisor.id).suprimido_em is None


def _meta(payload: dict, segredo: str) -> dict:
    corpo = json.dumps(payload).encode()
    return {"content": corpo, "headers": {"X-Hub-Signature-256": "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}}


PAYLOAD_META = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "999888777"}, "messages": [{"from": "5511999990000", "text": {"body": "SAIR"}}]}}]}]}


def test_meta_sem_assinatura_e_recusada(client):
    assert client.post("/api/v1/webhooks/whatsapp/meta", json=PAYLOAD_META).status_code == 403


def test_meta_com_assinatura_de_outro_segredo_e_recusada(client):
    assert client.post("/api/v1/webhooks/whatsapp/meta", **_meta(PAYLOAD_META, "segredo-do-atacante")).status_code == 403


def test_meta_com_corpo_adulterado_depois_de_assinado_e_recusada(client):
    pedido = _meta(PAYLOAD_META, APP_SECRET_META_TESTE)
    pedido["content"] = pedido["content"].replace(b"SAIR", b"OK!!")
    assert client.post("/api/v1/webhooks/whatsapp/meta", **pedido).status_code == 403


def test_meta_sem_app_secret_configurado_nunca_autoriza_nem_com_assinatura_calculada_com_segredo_vazio(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    assert client.post("/api/v1/webhooks/whatsapp/meta", **_meta(PAYLOAD_META, "")).status_code == 403


def test_meta_com_assinatura_valida_e_aceita(client):
    assert client.post("/api/v1/webhooks/whatsapp/meta", **_meta(PAYLOAD_META, APP_SECRET_META_TESTE)).status_code == 200
