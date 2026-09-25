"""Webhooks de saída do tenant a partir dos eventos de domínio (Fase 3).

Fluxo: `events.publicar` (outbox) → `events.processar_pendentes` chama
`enfileirar_entregas` → uma `EntregaWebhook` por assinatura interessada
(única por assinatura+evento) → `despachar_entregas` faz POST assinado
com retry e backoff.

Barreira de classificação: só eventos PUBLIC/INTERNAL saem por webhook.
CONFIDENTIAL/RESTRICTED (ex.: dado interno do comprador, Fase 10) nunca
são entregues a URL externa.

Assinatura: header `X-B2BON-Signature: t=<unix>,v1=<hex>` com
HMAC-SHA256 de `"<t>.<corpo>"` usando o segredo da assinatura.
"""

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.contexts.shared import events
from app.contexts.shared.canonical.base import DataClassification
from app.core.config import settings
from app.models.assinatura_webhook_tenant import AssinaturaWebhookTenant
from app.models.entrega_webhook import EntregaWebhook
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

CLASSIFICACOES_EXTERNALIZAVEIS = frozenset({DataClassification.PUBLIC, DataClassification.INTERNAL})
BACKOFF_MINUTOS = [1, 5, 15, 60, 360]
MAX_TENTATIVAS = len(BACKOFF_MINUTOS) + 1
TIMEOUT_SEGUNDOS = 10.0
TIPOS_VALIDOS = frozenset(str(t) for t in events.TipoEvento)

Enviar = Callable[[str, bytes, dict[str, str]], int]


def _validar_url(url: str) -> str:
    partes = urlparse(url)
    if partes.scheme not in ("https", "http") or not partes.netloc:
        raise ValidacaoFalhou("URL de webhook inválida.")
    if settings.e_ambiente_producao and partes.scheme != "https":
        raise ValidacaoFalhou("Em produção a URL de webhook precisa ser HTTPS.")
    return url


def criar_assinatura(db: Session, tenant_id: str, ator_id: str | None, url: str, eventos: list[str]) -> tuple[AssinaturaWebhookTenant, str]:
    invalidos = set(eventos) - TIPOS_VALIDOS
    if not eventos or invalidos:
        raise ValidacaoFalhou(f"Eventos inválidos: {sorted(invalidos) or 'nenhum informado'}.")
    segredo = "whsec_" + secrets.token_urlsafe(32)
    assinatura = AssinaturaWebhookTenant(tenant_id=tenant_id, url=_validar_url(url), eventos=sorted(set(eventos)), segredo=segredo, ativa=True)
    db.add(assinatura)
    db.flush()
    auditoria_service.registrar(db, tenant_id, "webhook_saida_criado", "assinatura_webhook_tenant", assinatura.id, ator_id, {"eventos": assinatura.eventos})
    db.commit()
    db.refresh(assinatura)
    return assinatura, segredo


def listar_assinaturas(db: Session, tenant_id: str) -> list[AssinaturaWebhookTenant]:
    return db.query(AssinaturaWebhookTenant).filter_by(tenant_id=tenant_id).order_by(AssinaturaWebhookTenant.id).all()


def desativar_assinatura(db: Session, tenant_id: str, ator_id: str | None, assinatura_id: int) -> AssinaturaWebhookTenant:
    assinatura = db.query(AssinaturaWebhookTenant).filter_by(id=assinatura_id, tenant_id=tenant_id).one_or_none()
    if assinatura is None:
        raise NaoEncontrado(f"Assinatura {assinatura_id} não encontrada")
    assinatura.ativa = False
    auditoria_service.registrar(db, tenant_id, "webhook_saida_desativado", "assinatura_webhook_tenant", assinatura.id, ator_id, {})
    db.commit()
    return assinatura


def listar_entregas(db: Session, tenant_id: str, assinatura_id: int, limite: int = 100) -> list[EntregaWebhook]:
    return (
        db.query(EntregaWebhook)
        .filter_by(tenant_id=tenant_id, assinatura_id=assinatura_id)
        .order_by(EntregaWebhook.id.desc())
        .limit(limite)
        .all()
    )


def enfileirar_entregas(db: Session, evento: events.EventoDominioDTO) -> None:
    """Handler do outbox. Idempotente por (assinatura, evento)."""
    if evento.classificacao not in CLASSIFICACOES_EXTERNALIZAVEIS:
        return
    assinaturas = db.query(AssinaturaWebhookTenant).filter_by(tenant_id=evento.tenant_id, ativa=True).all()
    for assinatura in assinaturas:
        if evento.tipo not in (assinatura.eventos or []):
            continue
        if db.query(EntregaWebhook).filter_by(assinatura_id=assinatura.id, evento_id=evento.evento_id).first():
            continue
        corpo = {
            "id": evento.evento_id,
            "type": evento.tipo,
            "version": evento.versao,
            "tenant_id": evento.tenant_id,
            "aggregate": {"type": evento.agregado_tipo, "id": evento.agregado_id},
            "occurred_at": evento.ocorrido_em.isoformat() if evento.ocorrido_em else None,
            "correlation_id": evento.correlation_id,
            "data": evento.payload,
        }
        db.add(EntregaWebhook(assinatura_id=assinatura.id, tenant_id=evento.tenant_id, evento_id=evento.evento_id, tipo=evento.tipo, payload=corpo, status="pendente", tentativas=0, proxima_tentativa_em=datetime.now(UTC)))
        db.flush()


def garantir_inscricao() -> None:
    for tipo in events.TipoEvento:
        events.inscrever(tipo, enfileirar_entregas)


def assinar(segredo: str, corpo: bytes, timestamp: int) -> str:
    digest = hmac.new(segredo.encode(), f"{timestamp}.".encode() + corpo, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _enviar_httpx(url: str, corpo: bytes, cabecalhos: dict[str, str]) -> int:
    with httpx.Client(timeout=TIMEOUT_SEGUNDOS, follow_redirects=False) as cliente:
        return cliente.post(url, content=corpo, headers=cabecalhos).status_code


def despachar_entregas(db: Session, enviar: Enviar | None = None, agora: datetime | None = None) -> dict:
    enviar = enviar or _enviar_httpx
    agora = agora or datetime.now(UTC)
    pendentes = (
        db.query(EntregaWebhook)
        .filter(EntregaWebhook.status == "pendente", EntregaWebhook.proxima_tentativa_em <= agora)
        .order_by(EntregaWebhook.id)
        .limit(200)
        .all()
    )
    resultado = {"entregues": 0, "reagendadas": 0, "desistidas": 0}
    for entrega in pendentes:
        assinatura = db.query(AssinaturaWebhookTenant).filter_by(id=entrega.assinatura_id).one_or_none()
        if assinatura is None or not assinatura.ativa:
            entrega.status = "desistida"
            entrega.ultimo_erro = "assinatura inativa"
            resultado["desistidas"] += 1
            continue
        corpo = json.dumps(entrega.payload, separators=(",", ":"), sort_keys=True).encode()
        cabecalhos = {
            "Content-Type": "application/json",
            "X-B2BON-Event": entrega.tipo,
            "X-B2BON-Delivery": str(entrega.id),
            "X-B2BON-Signature": assinar(assinatura.segredo, corpo, int(time.time())),
        }
        entrega.tentativas += 1
        try:
            status = enviar(assinatura.url, corpo, cabecalhos)
            entrega.ultimo_status_http = status
            sucesso = 200 <= status < 300
            erro = None if sucesso else f"HTTP {status}"
        except httpx.HTTPError as exc:
            sucesso, erro = False, f"{type(exc).__name__}: {exc}"[:500]
        if sucesso:
            entrega.status = "entregue"
            entrega.entregue_em = agora
            resultado["entregues"] += 1
        elif entrega.tentativas >= MAX_TENTATIVAS:
            entrega.status = "desistida"
            entrega.ultimo_erro = erro
            resultado["desistidas"] += 1
        else:
            entrega.ultimo_erro = erro
            entrega.proxima_tentativa_em = agora + timedelta(minutes=BACKOFF_MINUTOS[entrega.tentativas - 1])
            resultado["reagendadas"] += 1
    db.commit()
    return resultado
