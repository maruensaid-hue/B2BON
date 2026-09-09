import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.channels.email.stub import StubEmailProvider
from app.providers.payment.stub import StubPaymentProvider
from app.services import pagamento_licenca_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

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
    email = StubEmailProvider()
    pagamento, _ = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="pendente_pagamento"))
    db_session.commit()

    pagamento_id_externo = provider.aprovar(pagamento.preferencia_id_externo)
    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo, email)

    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one()
    assert licenca.status == "ativa"
    assert licenca.data_expiracao is not None
    dias_restantes = (licenca.data_expiracao - datetime.now(UTC).replace(tzinfo=None)).days
    assert 28 <= dias_restantes <= 30

    pagamento_atualizado = db_session.query(PagamentoLicenca).filter_by(id=pagamento.id).one()
    assert pagamento_atualizado.status == "aprovado"
    assert pagamento_atualizado.confirmado_em is not None


def test_webhook_aprovado_envia_email_de_agradecimento(db_session):
    plano = _tenant_e_plano(db_session)
    provider = StubPaymentProvider()
    email = StubEmailProvider()
    db_session.add(Usuario(tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin"))
    pagamento, _ = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="pendente_pagamento"))
    db_session.commit()

    pagamento_id_externo = provider.aprovar(pagamento.preferencia_id_externo)
    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo, email)

    assert len(email.envios) == 1
    assert email.envios[0]["destinatario"] == "admin@teste.com.br"
    assert "obrigado" in email.envios[0]["corpo"].lower()


def test_webhook_aprovado_limpa_declaracao_de_pagamento(db_session):
    """Se o usuário tinha se autodeclarado pagador enquanto suspenso, a
    confirmação real do webhook não precisa mais dessa carência própria."""
    plano = _tenant_e_plano(db_session)
    provider = StubPaymentProvider()
    email = StubEmailProvider()
    pagamento, _ = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)
    db_session.add(
        Licenca(
            tenant_id=TENANT_ID, plano_id=plano.id, status="ativa",
            declaracao_pagamento_em=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db_session.commit()

    pagamento_id_externo = provider.aprovar(pagamento.preferencia_id_externo)
    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo, email)

    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one()
    assert licenca.declaracao_pagamento_em is None


def test_webhook_duplicado_nao_reprocessa(db_session):
    """O Mercado Pago reenvia o webhook se a resposta demorar — não pode
    re-estender a licença nem duplicar o registro de confirmação."""
    plano = _tenant_e_plano(db_session)
    provider = StubPaymentProvider()
    email = StubEmailProvider()
    pagamento, _ = pagamento_licenca_service.iniciar(db_session, TENANT_ID, plano.id, "admin@teste.com.br", provider)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="pendente_pagamento"))
    db_session.commit()
    pagamento_id_externo = provider.aprovar(pagamento.preferencia_id_externo)

    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo, email)
    primeira_confirmacao = db_session.query(PagamentoLicenca).filter_by(id=pagamento.id).one().confirmado_em

    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo, email)
    segunda_confirmacao = db_session.query(PagamentoLicenca).filter_by(id=pagamento.id).one().confirmado_em

    assert primeira_confirmacao == segunda_confirmacao


def test_webhook_com_referencia_desconhecida_nao_derruba_nada(db_session):
    provider = StubPaymentProvider()
    email = StubEmailProvider()
    provider._preferencias["stub-pref-fantasma"] = {
        "referencia_externa": "999999",
        "valor": 100.0,
        "status": "pending",
        "pagamento_id": None,
    }
    pagamento_id_externo = provider.aprovar("stub-pref-fantasma")

    pagamento_licenca_service.confirmar_via_webhook(db_session, provider, pagamento_id_externo, email)  # não deve lançar


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


def test_declarar_pagamento_reativa_licenca_suspensa(db_session):
    plano = _tenant_e_plano(db_session)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="suspensa"))
    db_session.commit()

    licenca = pagamento_licenca_service.declarar_pagamento(db_session, TENANT_ID)

    assert licenca.status == "ativa"
    assert licenca.declaracao_pagamento_em is not None


def test_declarar_pagamento_rejeita_licenca_ja_ativa(db_session):
    plano = _tenant_e_plano(db_session)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="ativa"))
    db_session.commit()

    try:
        pagamento_licenca_service.declarar_pagamento(db_session, TENANT_ID)
        assert False, "deveria ter lançado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_declarar_pagamento_rejeita_sem_licenca(db_session):
    db_session.add(Tenant(id="tenant-sem-licenca-2", razao_social="Empresa Y"))
    db_session.commit()

    try:
        pagamento_licenca_service.declarar_pagamento(db_session, "tenant-sem-licenca-2")
        assert False, "deveria ter lançado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_enviar_lembretes_cobranca_pre_vencimento(db_session):
    plano = _tenant_e_plano(db_session)
    db_session.add(Usuario(tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin"))
    vencimento = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="ativa", data_expiracao=vencimento))
    db_session.commit()
    email = StubEmailProvider()

    resultado = pagamento_licenca_service.enviar_lembretes_cobranca(db_session, email)

    assert resultado["lembretes_enviados"] == 1
    assert len(email.envios) == 1
    assert "vence em 3 dias" in email.envios[0]["assunto"]
    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one()
    assert licenca.ultimo_lembrete_cobranca_em == datetime.now(UTC).date()


def test_enviar_lembretes_cobranca_pos_vencimento_dentro_da_carencia(db_session):
    plano = _tenant_e_plano(db_session)
    db_session.add(Usuario(tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin"))
    vencimento = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="ativa", data_expiracao=vencimento))
    db_session.commit()
    email = StubEmailProvider()

    resultado = pagamento_licenca_service.enviar_lembretes_cobranca(db_session, email)

    assert resultado["lembretes_enviados"] == 1
    assert "não identificamos" in email.envios[0]["assunto"].lower()


def test_enviar_lembretes_cobranca_nao_reenvia_no_mesmo_dia(db_session):
    plano = _tenant_e_plano(db_session)
    db_session.add(Usuario(tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin"))
    vencimento = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)
    db_session.add(
        Licenca(
            tenant_id=TENANT_ID, plano_id=plano.id, status="ativa", data_expiracao=vencimento,
            ultimo_lembrete_cobranca_em=datetime.now(UTC).date(),
        )
    )
    db_session.commit()
    email = StubEmailProvider()

    resultado = pagamento_licenca_service.enviar_lembretes_cobranca(db_session, email)

    assert resultado["lembretes_enviados"] == 0
    assert len(email.envios) == 0


def test_enviar_lembretes_cobranca_fora_da_janela_nao_envia(db_session):
    plano = _tenant_e_plano(db_session)
    db_session.add(Usuario(tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin"))
    vencimento = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=10)
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="ativa", data_expiracao=vencimento))
    db_session.commit()
    email = StubEmailProvider()

    resultado = pagamento_licenca_service.enviar_lembretes_cobranca(db_session, email)

    assert resultado["lembretes_enviados"] == 0
