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
            {"event": "delivered", "tenant_id": TENANT_ID, "mensagem_id": "1"},
            {"event": "bounce", "tenant_id": TENANT_ID, "mensagem_id": "2"},
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


# --- envio por API do próprio cliente: cada cliente assina os avisos com a chave dele ---------------------------------------------------


def _preparar_cliente(db_session, chave_publica_b64: str | None):
    from app.models.campanha import Campanha, CampanhaDestinatario
    from app.models.configuracao_email_api import ConfiguracaoEmailApi

    campanha = Campanha(tenant_id=TENANT_ID, nome="Do cliente", tipo="marketing", canais=["email"])
    outra = Campanha(tenant_id="outro-tenant", nome="De outro", tipo="marketing", canais=["email"])
    db_session.add_all([campanha, outra])
    db_session.flush()
    meus = [
        CampanhaDestinatario(tenant_id=TENANT_ID, campanha_id=campanha.id, nome=f"M{i}", email=f"m{i}@teste.com", status="enviado")
        for i in range(2)
    ]
    do_outro = CampanhaDestinatario(tenant_id="outro-tenant", campanha_id=outra.id, nome="O", email="o@teste.com", status="enviado")
    db_session.add_all([*meus, do_outro])
    if chave_publica_b64 is not None:
        db_session.add(ConfiguracaoEmailApi(tenant_id=TENANT_ID, chave_api="SG.x", remetente_email="v@c.com", chave_webhook=chave_publica_b64))
    db_session.commit()
    return meus, do_outro


def _enviar_eventos(client, chave_privada, eventos: list[dict], rota: str = "/api/v1/webhooks/envio/eventos"):
    payload = json.dumps(eventos).encode()
    timestamp = "1700000000"
    return client.post(
        rota,
        content=payload,
        headers={
            "content-type": "application/json",
            "x-twilio-email-event-webhook-signature": _assinar(chave_privada, timestamp, payload),
            "x-twilio-email-event-webhook-timestamp": timestamp,
        },
    )


def test_aviso_assinado_com_a_chave_do_cliente_marca_entrega_e_bounce(client, db_session) -> None:
    chave_privada, publica = _gerar_par_de_chaves()
    (primeiro, segundo), _ = _preparar_cliente(db_session, publica)

    resposta = _enviar_eventos(
        client,
        chave_privada,
        [
            {"event": "delivered", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(primeiro.id)},
            {"event": "bounce", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(segundo.id), "reason": "550 5.1.1 mailbox unavailable"},
        ],
    )

    assert resposta.status_code == 200
    db_session.expire_all()
    assert primeiro.entregue_em is not None and primeiro.bounce_em is None
    assert segundo.bounce_em is not None and segundo.motivo_bounce == "550 5.1.1 mailbox unavailable"


def test_chave_de_um_cliente_nao_forja_eventos_de_outro(client, db_session) -> None:
    chave_privada, publica = _gerar_par_de_chaves()
    (primeiro, _), do_outro = _preparar_cliente(db_session, publica)

    # Payload misto assinado com a chave do cliente: só o que é dele vale.
    resposta = _enviar_eventos(
        client,
        chave_privada,
        [
            {"event": "delivered", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(primeiro.id)},
            {"event": "bounce", "tenant_id": "outro-tenant", "campanha_destinatario_id": str(do_outro.id)},
        ],
    )
    assert resposta.status_code == 200
    db_session.expire_all()
    assert primeiro.entregue_em is not None
    assert do_outro.bounce_em is None and do_outro.entregue_em is None

    # Payload só do outro tenant (que não tem chave cadastrada), assinado com a chave do cliente: rejeitado.
    rejeitada = _enviar_eventos(client, chave_privada, [{"event": "bounce", "tenant_id": "outro-tenant", "campanha_destinatario_id": str(do_outro.id)}])
    assert rejeitada.status_code == 403
    db_session.expire_all()
    assert do_outro.bounce_em is None


def test_evento_do_cliente_que_aponta_para_destinatario_de_outro_tenant_e_ignorado(client, db_session) -> None:
    chave_privada, publica = _gerar_par_de_chaves()
    _, do_outro = _preparar_cliente(db_session, publica)

    resposta = _enviar_eventos(
        client, chave_privada, [{"event": "bounce", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(do_outro.id)}]
    )

    assert resposta.status_code == 200
    db_session.expire_all()
    assert do_outro.bounce_em is None  # a busca do destinatário é sempre dentro do tenant do evento


def test_aviso_assinado_com_chave_que_nao_e_a_do_cliente_e_rejeitado(client, db_session) -> None:
    _, publica_do_cliente = _gerar_par_de_chaves()
    outra_privada, _ = _gerar_par_de_chaves()
    (primeiro, _), _ = _preparar_cliente(db_session, publica_do_cliente)

    resposta = _enviar_eventos(client, outra_privada, [{"event": "bounce", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(primeiro.id)}])

    assert resposta.status_code == 403
    db_session.expire_all()
    assert primeiro.bounce_em is None


def test_cliente_sem_chave_de_verificacao_nao_tem_o_aviso_aceito(client, db_session) -> None:
    chave_privada, _ = _gerar_par_de_chaves()
    (primeiro, _), _ = _preparar_cliente(db_session, None)

    resposta = _enviar_eventos(client, chave_privada, [{"event": "bounce", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(primeiro.id)}])

    assert resposta.status_code == 403


def test_aviso_da_plataforma_tambem_marca_a_entrega_dentro_do_tenant(client, db_session, monkeypatch) -> None:
    chave_privada, publica_plataforma = _gerar_par_de_chaves()
    monkeypatch.setattr(settings, "sendgrid_webhook_verification_key", publica_plataforma)
    (primeiro, _), _ = _preparar_cliente(db_session, None)

    resposta = _enviar_eventos(
        client, chave_privada, [{"event": "delivered", "tenant_id": TENANT_ID, "campanha_destinatario_id": str(primeiro.id)}],
        rota="/api/v1/webhooks/sendgrid/eventos",  # o endereço antigo continua valendo
    )

    assert resposta.status_code == 200
    db_session.expire_all()
    assert primeiro.entregue_em is not None
