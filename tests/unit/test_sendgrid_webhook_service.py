import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.services import reputacao_service, sendgrid_webhook_service


def _gerar_par_de_chaves():
    chave_privada = ec.generate_private_key(ec.SECP256R1())
    chave_publica_der = chave_privada.public_key().public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return chave_privada, base64.b64encode(chave_publica_der).decode()


def _assinar(chave_privada, timestamp: str, payload: bytes) -> str:
    assinatura = chave_privada.sign(timestamp.encode() + payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(assinatura).decode()


def test_assinatura_valida_e_aceita() -> None:
    chave_privada, chave_publica_b64 = _gerar_par_de_chaves()
    payload = b'[{"event": "delivered"}]'
    timestamp = "1700000000"
    assinatura_b64 = _assinar(chave_privada, timestamp, payload)

    assert (
        sendgrid_webhook_service.verificar_assinatura(payload, assinatura_b64, timestamp, chave_publica_b64) is True
    )


def test_payload_adulterado_e_rejeitado() -> None:
    """Trava contra forjar bounce/spam em massa pra derrubar o canal de
    e-mail de um tenant à força — sem verificação, qualquer um poderia
    chamar o webhook direto."""
    chave_privada, chave_publica_b64 = _gerar_par_de_chaves()
    timestamp = "1700000000"
    assinatura_b64 = _assinar(chave_privada, timestamp, b'[{"event": "delivered"}]')

    payload_adulterado = b'[{"event": "bounce"}]'
    assert (
        sendgrid_webhook_service.verificar_assinatura(payload_adulterado, assinatura_b64, timestamp, chave_publica_b64)
        is False
    )


def test_headers_faltando_e_rejeitado() -> None:
    _, chave_publica_b64 = _gerar_par_de_chaves()
    assert sendgrid_webhook_service.verificar_assinatura(b"[]", None, "1700000000", chave_publica_b64) is False
    assert sendgrid_webhook_service.verificar_assinatura(b"[]", "assinatura-qualquer", None, chave_publica_b64) is False


def test_sem_chave_publica_configurada_e_rejeitado() -> None:
    assert sendgrid_webhook_service.verificar_assinatura(b"[]", "assinatura-qualquer", "1700000000", "") is False


def test_lixo_no_lugar_da_assinatura_nao_levanta_excecao() -> None:
    _, chave_publica_b64 = _gerar_par_de_chaves()
    assert (
        sendgrid_webhook_service.verificar_assinatura(b"[]", "!!!nao-e-base64!!!", "1700000000", chave_publica_b64)
        is False
    )


def test_processar_eventos_mapeia_tipo_e_agrupa_por_tenant(db_session) -> None:
    eventos = [
        {"event": "delivered", "tenant_id": "tenant-a"},
        {"event": "bounce", "tenant_id": "tenant-a"},
        {"event": "spamreport", "tenant_id": "tenant-a"},
        {"event": "open", "tenant_id": "tenant-a"},  # sem sinal de reputação, ignorado
        {"event": "dropped"},  # sem tenant_id, ignorado (não deveria acontecer, mas não derruba o batch)
    ]

    sendgrid_webhook_service.processar_eventos(db_session, eventos)

    saude = reputacao_service.status_saude(db_session, "tenant-a", "email")
    assert saude["enviados"] == 1
    assert saude["bounces"] == 1
    assert saude["spam_reports"] == 1
