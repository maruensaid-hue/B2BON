import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.models.assinatura_webhook_parceiro import AssinaturaWebhookParceiro
from app.models.evento_webhook_parceiro import EventoWebhookParceiro
from app.models.tenant import Tenant

_PROFUNDIDADE_MAXIMA_HIERARQUIA = 5
# Atraso antes de cada nova tentativa (1min, 5min, 15min, 1h, 6h) — 6
# tentativas no total (a inicial + 5 retentativas); se a 6ª ainda falhar,
# desiste (raio-X: webhook de saída pra Distribuidor, Fase 2 da hierarquia).
_BACKOFF_MINUTOS = [1, 5, 15, 60, 360]
_MAX_TENTATIVAS = 6


def _assinatura_ancestral(db: Session, tenant_id: str) -> AssinaturaWebhookParceiro | None:
    """Sobe a cadeia de `tenant_pai_id` a partir de `tenant_id` até achar
    uma assinatura de webhook ativa — mesmo padrão limitado em
    profundidade de `app.api.deps._e_ancestral`."""
    atual_id = tenant_id
    for _ in range(_PROFUNDIDADE_MAXIMA_HIERARQUIA):
        assinatura = db.query(AssinaturaWebhookParceiro).filter_by(tenant_id=atual_id, ativa=True).one_or_none()
        if assinatura is not None:
            return assinatura
        tenant = db.query(Tenant).filter_by(id=atual_id).one_or_none()
        if tenant is None or tenant.tenant_pai_id is None:
            return None
        atual_id = tenant.tenant_pai_id
    return None


def enfileirar_evento(db: Session, tenant_id: str, tipo_evento: str, payload: dict) -> None:
    """Chamado nos 4 pontos onde cada evento acontece de verdade
    (`criar_tenant_inicial`, `suspender_licencas_vencidas`,
    `atualizar_licenca`, `pagamento_licenca_service.confirmar_via_webhook`).
    Sem nenhuma assinatura ativa no caminho até a raiz da árvore, não cria
    nada — não faz sentido enfileirar evento pra tenant sem Distribuidor
    com integração configurada."""
    assinatura = _assinatura_ancestral(db, tenant_id)
    if assinatura is None:
        return
    db.add(
        EventoWebhookParceiro(assinatura_id=assinatura.id, tipo_evento=tipo_evento, payload_json=json.dumps(payload))
    )
    db.flush()


def _assinar(segredo: str, corpo: bytes) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def despachar_pendentes(db: Session) -> dict:
    """Cron entrypoint (`POST /cron/disparar-webhooks-parceiros`) — envia
    o que está devido, com o mesmo raciocínio de assinatura HMAC já usado
    (invertido) em `pagamento_licenca_service.verificar_assinatura_webhook`
    e `sendgrid_webhook_service.verificar_assinatura`: aqui o B2B ON
    assina, o Distribuidor verifica (`X-B2BON-Signature`)."""
    agora = datetime.now(UTC)
    pendentes = (
        db.query(EventoWebhookParceiro)
        .filter(
            EventoWebhookParceiro.entregue_em.is_(None),
            EventoWebhookParceiro.desistido_em.is_(None),
            EventoWebhookParceiro.proxima_tentativa_em <= agora,
        )
        .all()
    )

    entregues = 0
    com_nova_tentativa = 0
    desistencias = 0

    for evento in pendentes:
        assinatura = db.query(AssinaturaWebhookParceiro).filter_by(id=evento.assinatura_id).one_or_none()
        if assinatura is None or not assinatura.ativa:
            evento.desistido_em = agora
            desistencias += 1
            continue

        corpo = evento.payload_json.encode()
        try:
            resposta = httpx.post(
                assinatura.url_callback,
                content=corpo,
                headers={
                    "Content-Type": "application/json",
                    "X-B2BON-Signature": _assinar(assinatura.segredo, corpo),
                },
                timeout=10,
            )
            sucesso = 200 <= resposta.status_code < 300
        except httpx.HTTPError:
            sucesso = False

        if sucesso:
            evento.entregue_em = agora
            entregues += 1
            continue

        evento.tentativas += 1
        if evento.tentativas >= _MAX_TENTATIVAS:
            evento.desistido_em = agora
            desistencias += 1
        else:
            evento.proxima_tentativa_em = agora + timedelta(minutes=_BACKOFF_MINUTOS[evento.tentativas - 1])
            com_nova_tentativa += 1

    db.commit()
    return {"entregues": entregues, "com_nova_tentativa": com_nova_tentativa, "desistencias": desistencias}
