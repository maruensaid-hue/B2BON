import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.orm import Session

from app.services import reputacao_service

# SendGrid só manda sinal de entregabilidade de verdade pra esses três —
# "open"/"click" já têm rastreio próprio via pixel (rastreamento_service),
# e os demais (processed/deferred/unsubscribe) não mudam saúde do canal.
_MAPA_EVENTOS = {
    "delivered": "enviado",
    "bounce": "bounce",
    "dropped": "bounce",
    "spamreport": "spam_report",
}


def verificar_assinatura(payload: bytes, assinatura_b64: str | None, timestamp: str | None, chave_publica_b64: str) -> bool:
    """Signed Event Webhook do SendGrid — ECDSA (P-256) sobre
    `timestamp + payload`, chave pública gerada no painel ao ativar a opção
    (Settings > Mail Settings > Event Webhook > Signed Event Webhook
    Requests). Sem isso, qualquer um poderia forjar um bounce/spam report e
    derrubar o canal de e-mail de um tenant à força (equivalente ao golpe
    que a verificação do Mercado Pago evita do lado de pagamento)."""
    if not assinatura_b64 or not timestamp or not chave_publica_b64:
        return False
    try:
        chave_publica = serialization.load_der_public_key(base64.b64decode(chave_publica_b64))
        chave_publica.verify(
            base64.b64decode(assinatura_b64), timestamp.encode() + payload, ec.ECDSA(hashes.SHA256())
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def processar_eventos(db: Session, eventos: list[dict]) -> None:
    """`tenant_id` vem de `custom_args` anexado no envio
    (`SendGridEmailProvider.enviar`) — o SendGrid devolve esses argumentos
    como campo de primeiro nível no próprio evento (não aninhado sob
    `custom_args`), não confundir com o formato de envio."""
    for evento in eventos:
        tenant_id = evento.get("tenant_id")
        tipo_mapeado = _MAPA_EVENTOS.get(evento.get("event", ""))
        if not tenant_id or tipo_mapeado is None:
            continue
        reputacao_service.registrar_evento(db, tenant_id, "email", tipo_mapeado)
