import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
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


def test_evento_blocked_conta_como_bounce(db_session) -> None:
    """Raio-X 2026-09-16: "blocked" é o mesmo conceito de "entregue com
    erro" que bounce/dropped — antes ficava de fora do mapa e nunca
    pausava nada."""
    sendgrid_webhook_service.processar_eventos(db_session, [{"event": "blocked", "tenant_id": "tenant-b"}])

    saude = reputacao_service.status_saude(db_session, "tenant-b", "email")
    assert saude["bounces"] == 1


def _criar_mensagem_com_decisor(db_session, tenant_id: str) -> Mensagem:
    conta = Conta(tenant_id=tenant_id, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, nome="Fulano", email="fulano@teste.com")
    db_session.add(decisor)
    db_session.flush()
    mensagem = Mensagem(
        tenant_id=tenant_id, decisor_id=decisor.id, canal="email", conteudo="Oi", status="enviado",
    )
    db_session.add(mensagem)
    db_session.commit()
    return mensagem


def test_bounce_grava_na_mensagem_correlacionada_por_mensagem_id(db_session) -> None:
    """Raio-X 2026-09-16 (Relatório de Entrega): sem `mensagem_id` no
    evento, o bounce só pausava o canal — agora também marca a mensagem
    exata, pra dar pra saber qual contato corrigir/excluir."""
    mensagem = _criar_mensagem_com_decisor(db_session, "tenant-c")

    sendgrid_webhook_service.processar_eventos(
        db_session,
        [{"event": "bounce", "tenant_id": "tenant-c", "mensagem_id": str(mensagem.id), "reason": "550 mailbox não existe"}],
    )

    db_session.refresh(mensagem)
    assert mensagem.bounce_em is not None
    assert mensagem.motivo_bounce == "550 mailbox não existe"


def test_bounce_grava_no_destinatario_de_campanha_correlacionado(db_session) -> None:
    campanha = Campanha(tenant_id="tenant-d", nome="Campanha", tipo="marketing", canais=["email"])
    db_session.add(campanha)
    db_session.flush()
    destinatario = CampanhaDestinatario(
        tenant_id="tenant-d", campanha_id=campanha.id, nome="Ciclano", email="ciclano@teste.com", status="enviado",
    )
    db_session.add(destinatario)
    db_session.commit()

    sendgrid_webhook_service.processar_eventos(
        db_session,
        [{"event": "dropped", "tenant_id": "tenant-d", "campanha_destinatario_id": str(destinatario.id)}],
    )

    db_session.refresh(destinatario)
    assert destinatario.bounce_em is not None


def test_evento_sem_mensagem_id_nao_levanta_excecao(db_session) -> None:
    """Evento de bounce legítimo (ex.: e-mail de sistema, fora do fluxo de
    cadência/campanha) sem `mensagem_id`/`campanha_destinatario_id` só
    não grava nada por contato — continua pausando o canal normalmente."""
    sendgrid_webhook_service.processar_eventos(db_session, [{"event": "bounce", "tenant_id": "tenant-e"}])

    assert reputacao_service.status_saude(db_session, "tenant-e", "email")["bounces"] == 1
