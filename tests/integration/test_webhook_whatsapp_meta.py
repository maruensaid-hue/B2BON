from app.core.config import settings
from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp

TENANT_ID = "tenant-teste"


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

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", json=payload)

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

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", json=payload)

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

    resposta = client.post("/api/v1/webhooks/whatsapp/meta", json=payload)

    assert resposta.status_code == 200
