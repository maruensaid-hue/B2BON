import hashlib
import hmac
import json

from app.core.config import settings
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp

TENANT_ID = "tenant-teste"


def _assinado(payload: dict, segredo: str | None = None) -> dict:
    """Corpo bruto + `X-Hub-Signature-256` como a Meta envia."""
    corpo = json.dumps(payload).encode()
    chave = (segredo if segredo is not None else settings.whatsapp_app_secret).encode()
    return {"content": corpo, "headers": {"X-Hub-Signature-256": "sha256=" + hmac.new(chave, corpo, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}}


def test_handshake_com_verify_token_correto_eco_o_challenge(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_webhook_verify_token", "token-secreto")

    resposta = client.get(
        "/api/v1/webhooks/whatsapp/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "token-secreto", "hub.challenge": "12345"},
    )

    assert resposta.status_code == 200
    assert resposta.text == "12345"


def test_handshake_com_verify_token_errado_e_rejeitado(client, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_webhook_verify_token", "token-secreto")

    resposta = client.get(
        "/api/v1/webhooks/whatsapp/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "token-errado", "hub.challenge": "12345"},
    )

    assert resposta.status_code == 403


def test_payload_real_da_meta_resolve_tenant_via_phone_number_id_e_processa_optout(
    client, db_session, onboarding_completo, criar_conta_com_decisor, criar_cadencia, monkeypatch, fake_whatsapp
):
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    db_session.add(
        ConfiguracaoWhatsApp(
            tenant_id=TENANT_ID, access_token="token-fake", phone_number_id="999888777", business_account_id="waba-1"
        )
    )
    db_session.commit()
    monkeypatch.setattr("app.api.v1.webhooks.resolver_whatsapp_provider", lambda tenant_id, db: fake_whatsapp)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "999888777"},
                            "messages": [{"from": decisor.telefone, "type": "text", "text": {"body": "SAIR"}}],
                        },
                    }
                ],
            }
        ],
    }

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", **_assinado(payload))

    assert resposta.status_code == 200
    assert resposta.json() == {"recebido": True}


def test_payload_com_phone_number_id_desconhecido_e_ignorado_sem_erro(client):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "numero-nunca-configurado"},
                            "messages": [{"from": "+5511999990000", "type": "text", "text": {"body": "oi"}}],
                        }
                    }
                ]
            }
        ]
    }

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", **_assinado(payload))

    assert resposta.status_code == 200


def test_payload_de_status_sem_messages_e_ignorado_sem_erro(client):
    """Confirmações de entrega (`statuses`) chegam no mesmo formato de
    payload, mas sem a chave `messages` — não deve derrubar o webhook."""
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "999888777"},
                            "statuses": [{"id": "abc", "status": "delivered"}],
                        }
                    }
                ]
            }
        ]
    }

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", **_assinado(payload))

    assert resposta.status_code == 200


def _payload_resposta(phone_number_id: str, remetente: str, texto: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"phone_number_id": phone_number_id},
            "messages": [{"from": remetente, "type": "text", "text": {"body": texto}}],
        }}]}],
    }


def test_resposta_da_meta_acha_o_tenant_e_o_contato_e_para_so_a_cadencia_de_quem_respondeu(
    client, db_session, onboarding_completo, criar_conta_com_decisor, criar_cadencia, monkeypatch, fake_whatsapp
):
    """Visto em produção em 09/11/2026: nenhuma resposta de WhatsApp era tratada. O ID do número é cifrado (a busca do tenant comparava o
    valor cifrado e nunca achava) e o remetente chega como "5511993495349" enquanto o contato está como "11993495349". Também confere que
    "parar a cadência se o cliente responder" vale só para quem respondeu: o outro contato da lista segue recebendo."""
    from app.models.mensagem import Mensagem

    conta_a, quem_responde = criar_conta_com_decisor(telefone="11993495349")
    conta_b, outro = criar_conta_com_decisor(telefone="(21) 98888-7777", email="outro@empresab.com.br")
    cadencia = criar_cadencia(cancelar_ao_responder=True)
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_a.id, conta_b.id]})
    db_session.add(ConfiguracaoWhatsApp(tenant_id=TENANT_ID, access_token="token-fake", phone_number_id="999888777", business_account_id="waba-1"))
    db_session.commit()
    monkeypatch.setattr("app.api.v1.webhooks.resolver_whatsapp_provider", lambda tenant_id, db: fake_whatsapp)
    id_quem_responde, id_outro = quem_responde.id, outro.id

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", **_assinado(_payload_resposta("999888777", "5511993495349", "Tenho interesse, me liga")))

    assert resposta.status_code == 200
    db_session.expire_all()
    status_de = lambda decisor_id: {m.status for m in db_session.query(Mensagem).filter_by(decisor_id=decisor_id).all()}  # noqa: E731
    assert status_de(id_quem_responde) == {"cancelado"}
    assert "cancelado" not in status_de(id_outro)


def test_remetente_sem_o_nono_digito_ainda_acha_o_contato(client, db_session, onboarding_completo, criar_conta_com_decisor, monkeypatch, fake_whatsapp):
    from app.api.v1.webhooks import _decisor_pelo_telefone

    _, decisor = criar_conta_com_decisor(telefone="+55 11 99349-5349")

    assert _decisor_pelo_telefone(db_session, TENANT_ID, "551193495349").id == decisor.id
    assert _decisor_pelo_telefone(db_session, TENANT_ID, "5511993495349").id == decisor.id
    assert _decisor_pelo_telefone(db_session, TENANT_ID, "5521993495349") is None


def test_hash_do_numero_e_gravado_tambem_quando_a_configuracao_e_atualizada(client, db_session):
    from app.models.configuracao_whatsapp import hash_phone_number_id

    client.put("/api/v1/configuracao-whatsapp", json={"phone_number_id": "111", "business_account_id": "456", "access_token": "segredo-super-longo"})
    client.put("/api/v1/configuracao-whatsapp", json={"phone_number_id": "222", "business_account_id": "456"})

    config = db_session.query(ConfiguracaoWhatsApp).filter_by(tenant_id=TENANT_ID).one()
    db_session.refresh(config)
    assert config.phone_number_id_hash == hash_phone_number_id("222")
