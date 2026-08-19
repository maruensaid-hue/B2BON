import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.providers.payment.stub import StubPaymentProvider
from app.services import pagamento_licenca_service

TENANT_ID = "tenant-teste"


def _tenant_e_plano(db_session) -> Plano:
    if db_session.query(Tenant).filter_by(id=TENANT_ID).one_or_none() is None:
        db_session.add(Tenant(id=TENANT_ID, razao_social="Empresa Teste"))
    plano = Plano(nome=f"Plano {db_session.query(Plano).count() + 1}", franquia_contas_mes=500, max_usuarios=20, preco_mensal=499.0)
    db_session.add(plano)
    db_session.commit()
    return plano


def test_iniciar_cria_pagamento_pendente_e_devolve_checkout_url(db_session):
    plano = _tenant_e_plano(db_session)
    provider = StubPaymentProvider()

    pagamento, checkout_url = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)

    assert pagamento.status == "pendente"
    assert pagamento.preferencia_id_externo.startswith("stub-pref-")
    assert checkout_url == f"https://checkout.stub.local/{pagamento.preferencia_id_externo}"


def test_iniciar_com_plano_gratuito_ativa_na_hora_sem_checkout(db_session):
    """Raio-X de produção real: o Mercado Pago recusa criar uma
    preferência de cobrança de valor zero (400 Bad Request) — plano
    gratuito (ex.: POC) não pode nem tentar passar pelo checkout."""
    if db_session.query(Tenant).filter_by(id=TENANT_ID).one_or_none() is None:
        db_session.add(Tenant(id=TENANT_ID, razao_social="Empresa Teste"))
    plano_gratuito = Plano(nome="POC", franquia_contas_mes=50, max_usuarios=3, preco_mensal=0.0)
    db_session.add(plano_gratuito)
    db_session.commit()
    provider = StubPaymentProvider()

    pagamento, checkout_url = pagamento_licenca_service.iniciar(
        db_session, TENANT_ID, plano_gratuito.id, "admin@teste.com.br", provider
    )

    assert checkout_url is None
    assert pagamento.status == "aprovado"
    assert pagamento.confirmado_em is not None
    assert provider._contador == 0  # criar_preferencia nunca foi chamado

    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one()
    assert licenca.status == "ativa"
    assert licenca.plano_id == plano_gratuito.id
    assert licenca.data_expiracao is not None


def test_webhook_aprovado_ativa_a_licenca(db_session):
    plano = _tenant_e_plano(db_session)
    provider = StubPaymentProvider()
    pagamento, _ = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="pendente_pagamento"))
    db_session.commit()

    pagamento_id_externo = provider.aprovar(pagamento.preferencia_id_externo)
    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo)

    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one()
    assert licenca.status == "ativa"
    assert licenca.data_expiracao is not None
    dias_restantes = (licenca.data_expiracao - datetime.now(UTC).replace(tzinfo=None)).days
    assert 28 <= dias_restantes <= 30

    pagamento_atualizado = db_session.query(PagamentoLicenca).filter_by(id=pagamento.id).one()
    assert pagamento_atualizado.status == "aprovado"
    assert pagamento_atualizado.confirmado_em is not None


def test_webhook_duplicado_nao_reprocessa(db_session):
    """O Mercado Pago reenvia o webhook se a resposta demorar — não pode
    re-estender a licença nem duplicar o registro de confirmação."""
    plano = _tenant_e_plano(db_session)
    provider = StubPaymentProvider()
    pagamento, _ = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="pendente_pagamento"))
    db_session.commit()
    pagamento_id_externo = provider.aprovar(pagamento.preferencia_id_externo)

    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo)
    primeira_confirmacao = db_session.query(PagamentoLicenca).filter_by(id=pagamento.id).one().confirmado_em

    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo)
    segunda_confirmacao = db_session.query(PagamentoLicenca).filter_by(id=pagamento.id).one().confirmado_em

    assert primeira_confirmacao == segunda_confirmacao


def test_webhook_com_referencia_desconhecida_nao_derruba_nada(db_session):
    provider = StubPaymentProvider()
    provider._preferencias["stub-pref-fantasma"] = {
        "referencia_externa": "999999",
        "valor": 100.0,
        "status": "pending",
        "pagamento_id": None,
    }
    pagamento_id_externo = provider.aprovar("stub-pref-fantasma")

    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo)  # não deve lançar


def test_verificar_assinatura_webhook_aceita_assinatura_valida():
    segredo = "segredo-de-teste"
    payment_id = "123456"
    ts = "1700000000"
    request_id = "req-abc"
    manifest = f"id:{payment_id.lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(segredo.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    x_signature = f"ts={ts},v1={v1}"

    assert pagamento_licenca_service.verificar_assinatura_webhook(x_signature, request_id, payment_id, segredo)


def test_verificar_assinatura_webhook_rejeita_assinatura_forjada():
    x_signature = "ts=1700000000,v1=0000000000000000000000000000000000000000000000000000000000000000"

    assert not pagamento_licenca_service.verificar_assinatura_webhook(
        x_signature, "req-abc", "123456", "segredo-de-teste"
    )


def test_verificar_assinatura_webhook_rejeita_sem_segredo_configurado():
    """`mercadopago_webhook_secret` vazio nunca autoriza — mesmo padrão do
    `cron_secret`."""
    x_signature = "ts=1700000000,v1=qualquercoisa"

    assert not pagamento_licenca_service.verificar_assinatura_webhook(x_signature, "req-abc", "123456", "")


def test_status_licenca_sem_licenca(db_session):
    db_session.add(Tenant(id="tenant-sem-licenca", razao_social="Empresa X"))
    db_session.commit()

    assert pagamento_licenca_service.status_licenca(db_session, "tenant-sem-licenca") == "sem_licenca"
