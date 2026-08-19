import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.models.assinatura_webhook_parceiro import AssinaturaWebhookParceiro
from app.models.evento_webhook_parceiro import EventoWebhookParceiro
from app.models.tenant import Tenant
from app.services import webhook_parceiro_service


def _criar_arvore(db_session, com_assinatura: bool = True) -> tuple[str, AssinaturaWebhookParceiro | None]:
    distribuidor = Tenant(id="distribuidor-wh", razao_social="Distribuidor WH", tipo="distribuidor")
    revendedor = Tenant(
        id="revenda-wh", razao_social="Revenda WH", tipo="revendedor", tenant_pai_id="distribuidor-wh"
    )
    cliente = Tenant(id="cliente-wh", razao_social="Cliente WH", tipo="cliente", tenant_pai_id="revenda-wh")
    db_session.add_all([distribuidor, revendedor, cliente])
    db_session.flush()

    assinatura = None
    if com_assinatura:
        assinatura = AssinaturaWebhookParceiro(
            tenant_id="distribuidor-wh", url_callback="https://exemplo.com.br/webhook", segredo="segredo-teste"
        )
        db_session.add(assinatura)
        db_session.flush()

    db_session.commit()
    return "cliente-wh", assinatura


def test_enfileirar_evento_sem_assinatura_no_caminho_nao_cria_nada(db_session) -> None:
    tenant_id, _ = _criar_arvore(db_session, com_assinatura=False)

    webhook_parceiro_service.enfileirar_evento(db_session, tenant_id, "tenant_provisionado", {"x": 1})

    assert db_session.query(EventoWebhookParceiro).count() == 0


def test_enfileirar_evento_acha_assinatura_ancestral(db_session) -> None:
    tenant_id, assinatura = _criar_arvore(db_session)

    webhook_parceiro_service.enfileirar_evento(db_session, tenant_id, "tenant_provisionado", {"tenant_id": tenant_id})
    db_session.commit()

    evento = db_session.query(EventoWebhookParceiro).one()
    assert evento.assinatura_id == assinatura.id
    assert evento.tipo_evento == "tenant_provisionado"
    assert json.loads(evento.payload_json) == {"tenant_id": tenant_id}


def test_despachar_pendentes_sucesso_marca_entregue_e_assina_com_hmac(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, assinatura = _criar_arvore(db_session)
    webhook_parceiro_service.enfileirar_evento(db_session, tenant_id, "pagamento_confirmado", {"tenant_id": tenant_id})
    db_session.commit()

    capturado = {}

    def _post_falso(url, content, headers, timeout):
        capturado.update(url=url, content=content, headers=headers)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "post", _post_falso)

    resultado = webhook_parceiro_service.despachar_pendentes(db_session)

    assert resultado == {"entregues": 1, "com_nova_tentativa": 0, "desistencias": 0}
    evento = db_session.query(EventoWebhookParceiro).one()
    assert evento.entregue_em is not None
    assert capturado["url"] == "https://exemplo.com.br/webhook"
    assinatura_esperada = "sha256=" + hmac.new(b"segredo-teste", capturado["content"], hashlib.sha256).hexdigest()
    assert capturado["headers"]["X-B2BON-Signature"] == assinatura_esperada


def test_despachar_pendentes_falha_agenda_proxima_tentativa_com_backoff(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, _ = _criar_arvore(db_session)
    webhook_parceiro_service.enfileirar_evento(db_session, tenant_id, "tenant_provisionado", {})
    db_session.commit()

    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(500))

    resultado = webhook_parceiro_service.despachar_pendentes(db_session)

    assert resultado == {"entregues": 0, "com_nova_tentativa": 1, "desistencias": 0}
    evento = db_session.query(EventoWebhookParceiro).one()
    assert evento.tentativas == 1
    assert evento.entregue_em is None
    assert evento.desistido_em is None
    assert evento.proxima_tentativa_em > datetime.now(UTC).replace(tzinfo=None)


def test_despachar_pendentes_erro_de_rede_tambem_conta_como_falha(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, _ = _criar_arvore(db_session)
    webhook_parceiro_service.enfileirar_evento(db_session, tenant_id, "tenant_provisionado", {})
    db_session.commit()

    def _post_com_erro(*args, **kwargs):
        raise httpx.ConnectError("recusado")

    monkeypatch.setattr(httpx, "post", _post_com_erro)

    resultado = webhook_parceiro_service.despachar_pendentes(db_session)

    assert resultado["com_nova_tentativa"] == 1


def test_despachar_pendentes_desiste_apos_max_tentativas(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, assinatura = _criar_arvore(db_session)
    evento = EventoWebhookParceiro(
        assinatura_id=assinatura.id, tipo_evento="tenant_provisionado", payload_json="{}", tentativas=5
    )
    db_session.add(evento)
    db_session.commit()

    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(500))

    resultado = webhook_parceiro_service.despachar_pendentes(db_session)

    assert resultado == {"entregues": 0, "com_nova_tentativa": 0, "desistencias": 1}
    db_session.refresh(evento)
    assert evento.tentativas == 6
    assert evento.desistido_em is not None


def test_despachar_pendentes_ignora_evento_nao_devido_ainda(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, assinatura = _criar_arvore(db_session)
    evento = EventoWebhookParceiro(
        assinatura_id=assinatura.id, tipo_evento="tenant_provisionado", payload_json="{}",
        proxima_tentativa_em=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(evento)
    db_session.commit()

    chamado = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: chamado.append(1) or httpx.Response(200))

    resultado = webhook_parceiro_service.despachar_pendentes(db_session)

    assert resultado == {"entregues": 0, "com_nova_tentativa": 0, "desistencias": 0}
    assert chamado == []


def test_despachar_pendentes_assinatura_inativa_desiste_sem_tentar(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, assinatura = _criar_arvore(db_session)
    assinatura.ativa = False
    evento = EventoWebhookParceiro(assinatura_id=assinatura.id, tipo_evento="tenant_provisionado", payload_json="{}")
    db_session.add(evento)
    db_session.commit()

    chamado = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: chamado.append(1) or httpx.Response(200))

    resultado = webhook_parceiro_service.despachar_pendentes(db_session)

    assert resultado["desistencias"] == 1
    assert chamado == []
