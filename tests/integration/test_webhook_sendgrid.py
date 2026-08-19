import base64
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import settings

TENANT_ID = "tenant-teste"


def _gerar_par_de_chaves():
    chave_privada = ec.generate_private_key(ec.SECP256R1())
    chave_publica_der = chave_privada.public_key().public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return chave_privada, base64.b64encode(chave_publica_der).decode()


def _assinar(chave_privada, timestamp: str, payload: bytes) -> str:
    assinatura = chave_privada.sign(timestamp.encode() + payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(assinatura).decode()


def test_eventos_com_assinatura_valida_atualizam_saude_do_canal(client, monkeypatch) -> None:
    chave_privada, chave_publica_b64 = _gerar_par_de_chaves()
    monkeypatch.setattr(settings, "sendgrid_webhook_verification_key", chave_publica_b64)

    payload = json.dumps(
        [
            {"event": "delivered", "tenant_id": TENANT_ID},
            {"event": "bounce", "tenant_id": TENANT_ID},
        ]
    ).encode()
    timestamp = "1700000000"
    assinatura = _assinar(chave_privada, timestamp, payload)

    resposta = client.post(
        "/api/v1/webhooks/sendgrid/eventos",
        content=payload,
        headers={
            "content-type": "application/json",
            "x-twilio-email-event-webhook-signature": assinatura,
            "x-twilio-email-event-webhook-timestamp": timestamp,
        },
    )

    assert resposta.status_code == 200
    saude = client.get("/api/v1/canais/email/saude").json()
    assert saude["enviados"] == 1
    assert saude["bounces"] == 1


def test_assinatura_invalida_e_rejeitada_com_403(client, monkeypatch) -> None:
    """Trava contra forjar bounce/spam em massa via essa URL pública — sem
    verificar a assinatura, qualquer um derrubaria o canal de e-mail de
    qualquer tenant só adivinhando o formato do payload."""
    _, chave_publica_b64 = _gerar_par_de_chaves()
    monkeypatch.setattr(settings, "sendgrid_webhook_verification_key", chave_publica_b64)

    resposta = client.post(
        "/api/v1/webhooks/sendgrid/eventos",
        content=json.dumps([{"event": "bounce", "tenant_id": TENANT_ID}]).encode(),
        headers={
            "content-type": "application/json",
            "x-twilio-email-event-webhook-signature": "assinatura-forjada",
            "x-twilio-email-event-webhook-timestamp": "1700000000",
        },
    )

    assert resposta.status_code == 403


def test_sem_chave_configurada_rejeita_qualquer_chamada(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "sendgrid_webhook_verification_key", "")

    resposta = client.post(
        "/api/v1/webhooks/sendgrid/eventos",
        content=b"[]",
        headers={"content-type": "application/json"},
    )

    assert resposta.status_code == 403
