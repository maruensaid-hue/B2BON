import base64
import json
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.orm import Session

from app.models.campanha import CampanhaDestinatario
from app.models.configuracao_email_api import ConfiguracaoEmailApi
from app.models.mensagem import Mensagem
from app.services import reputacao_service

# SendGrid só manda sinal de entregabilidade de verdade pra esses quatro —
# "open"/"click" já têm rastreio próprio via pixel (rastreamento_service),
# e os demais (processed/deferred/unsubscribe) não mudam saúde do canal.
# "blocked" (bloqueado pelo provedor do destinatário) é o mesmo conceito
# de "entregue com erro" que "bounce"/"dropped" — raio-X 2026-09-16.
_MAPA_EVENTOS = {
    "delivered": "enviado",
    "bounce": "bounce",
    "dropped": "bounce",
    "blocked": "bounce",
    "spamreport": "spam_report",
}

# Só esses tipos de evento representam "entrega com erro" num contato
# específico — usados pra gravar `bounce_em`/`motivo_bounce` na
# Mensagem/CampanhaDestinatario exata (raio-X 2026-09-16: Relatório de
# Entrega, distinto do contador agregado que já existia).
_EVENTOS_COM_CONTATO_PROBLEMATICO = {"bounce", "dropped", "blocked", "spamreport"}


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


def _registrar_contato_problematico(db: Session, evento: dict) -> None:
    """Grava `bounce_em`/`motivo_bounce` na `Mensagem` ou
    `CampanhaDestinatario` exata que gerou o evento — `mensagem_id`/
    `campanha_destinatario_id` também vêm ecoados como campo de primeiro
    nível (mesmo raciocínio de `tenant_id`), só presentes se o envio
    original passou por `SendGridEmailProvider.enviar` com um desses
    parâmetros preenchidos. Sem isso, `reputacao_service` só sabe pausar
    o canal inteiro — não dá pra saber qual contato corrigir/excluir."""
    motivo = evento.get("reason") or evento.get("event", "")
    agora = datetime.now(UTC)

    mensagem_id = evento.get("mensagem_id")
    if mensagem_id is not None:
        mensagem = db.query(Mensagem).filter_by(id=int(mensagem_id), tenant_id=evento.get("tenant_id")).one_or_none()
        if mensagem is not None:
            mensagem.bounce_em = agora
            mensagem.motivo_bounce = motivo
        return

    campanha_destinatario_id = evento.get("campanha_destinatario_id")
    if campanha_destinatario_id is not None:
        destinatario = (
            db.query(CampanhaDestinatario)
            .filter_by(id=int(campanha_destinatario_id), tenant_id=evento.get("tenant_id"))
            .one_or_none()
        )
        if destinatario is not None:
            destinatario.bounce_em = agora
            destinatario.motivo_bounce = motivo


def _registrar_entrega(db: Session, evento: dict) -> None:
    """Entrega confirmada pelo serviço de envio (`delivered`): guarda o momento no e-mail exato, para o relatório mostrar "Entregue" — antes só alimentava o
    contador agregado de reputação. Sempre dentro do tenant do evento: um cliente nunca marca e-mail de outro."""
    agora = datetime.now(UTC)
    mensagem_id = evento.get("mensagem_id")
    if mensagem_id is not None:
        mensagem = db.query(Mensagem).filter_by(id=int(mensagem_id), tenant_id=evento.get("tenant_id")).one_or_none()
        if mensagem is not None and mensagem.entregue_em is None:
            mensagem.entregue_em = agora
        return
    campanha_destinatario_id = evento.get("campanha_destinatario_id")
    if campanha_destinatario_id is not None:
        destinatario = (
            db.query(CampanhaDestinatario)
            .filter_by(id=int(campanha_destinatario_id), tenant_id=evento.get("tenant_id"))
            .one_or_none()
        )
        if destinatario is not None and destinatario.entregue_em is None:
            destinatario.entregue_em = agora


def processar_eventos(db: Session, eventos: list[dict]) -> None:
    """`tenant_id` vem de `custom_args` anexado no envio
    (`SendGridEmailProvider.enviar`) — o SendGrid devolve esses argumentos
    como campo de primeiro nível no próprio evento (não aninhado sob
    `custom_args`), não confundir com o formato de envio."""
    for evento in eventos:
        tenant_id = evento.get("tenant_id")
        tipo_evento = evento.get("event", "")
        tipo_mapeado = _MAPA_EVENTOS.get(tipo_evento)
        if not tenant_id or tipo_mapeado is None:
            continue
        # Só e-mail de cadência/campanha alimenta a reputação do canal. E-mail
        # de sistema (convite, cobrança, boas-vindas) sai pelo mesmo SendGrid
        # com o `tenant_id` do assinante, mas não tem `mensagem_id`/
        # `campanha_destinatario_id` — contá-lo pausava o outreach do tenant
        # por bounce de um convite digitado errado (incidente 2026-10-05).
        if evento.get("mensagem_id") is None and evento.get("campanha_destinatario_id") is None:
            continue
        reputacao_service.registrar_evento(db, tenant_id, "email", tipo_mapeado)
        if tipo_evento in _EVENTOS_COM_CONTATO_PROBLEMATICO:
            _registrar_contato_problematico(db, evento)
        elif tipo_evento == "delivered":
            _registrar_entrega(db, evento)
    db.commit()


def _chave_de_verificacao_do_tenant(db: Session, tenant_id: str) -> str | None:
    try:
        config = db.query(ConfiguracaoEmailApi).filter_by(tenant_id=tenant_id).one_or_none()
    except InvalidToken:  # chave cifrada com outra chave de criptografia: sem como validar, então não aceita
        return None
    return config.chave_webhook if config is not None else None


def autenticar_e_processar(
    db: Session, corpo: bytes, assinatura_b64: str | None, timestamp: str | None, chave_da_plataforma: str
) -> bool:
    """Valida a assinatura do aviso de eventos e só então processa. Dois emissores legítimos: a conta da plataforma (chave global; vale para qualquer tenant,
    pois é a própria plataforma que envia) e a conta de cada cliente (chave dele, em `ConfiguracaoEmailApi`). Os eventos do cliente são lidos de forma
    não confiável só para descobrir de quais tenants são; se a assinatura bate com a chave de um deles, **apenas os eventos desse tenant** são processados — assim
    uma chave de cliente nunca serve para forjar entrega/bounce de outro."""
    if verificar_assinatura(corpo, assinatura_b64, timestamp, chave_da_plataforma):
        processar_eventos(db, json.loads(corpo))
        return True
    try:
        eventos = json.loads(corpo)
    except ValueError:
        return False
    if not isinstance(eventos, list):
        return False
    tenants = sorted({e["tenant_id"] for e in eventos if isinstance(e, dict) and isinstance(e.get("tenant_id"), str)})
    for tenant_id in tenants:
        chave = _chave_de_verificacao_do_tenant(db, tenant_id)
        if chave and verificar_assinatura(corpo, assinatura_b64, timestamp, chave):
            processar_eventos(db, [e for e in eventos if isinstance(e, dict) and e.get("tenant_id") == tenant_id])
            return True
    return False
