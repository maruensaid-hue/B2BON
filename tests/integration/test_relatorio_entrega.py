from datetime import UTC, datetime

from app.models.mensagem import Mensagem
from app.services import aprovacao_service
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT_ID = "tenant-teste"


def test_relatorio_entrega_retorna_saude_e_indicadores(client, onboarding_completo):
    """Raio-X 2026-09-16 — combina dados que já existiam dispersos
    (saúde do canal de e-mail, taxa de abertura/resposta), antes sem
    nenhuma tela expondo isso."""
    resposta = client.get("/api/v1/relatorio-entrega")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["saude_email"]["canal"] == "email"
    assert corpo["saude_email"]["pausado"] is False
    assert "taxa_resposta_por_canal" in corpo
    assert corpo["contatos_com_bounce"] == []


def test_relatorio_entrega_lista_contato_com_bounce(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    conta, decisor = criar_conta_com_decisor()
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi", StubPlanLimitsProvider(),
    )
    mensagem.status = "enviado"
    mensagem.bounce_em = datetime.now(UTC)
    mensagem.motivo_bounce = "550 mailbox não existe"
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega").json()

    assert len(corpo["contatos_com_bounce"]) == 1
    contato = corpo["contatos_com_bounce"][0]
    assert contato["decisor_id"] == decisor.id
    assert contato["email"] == decisor.email
    assert contato["motivo_bounce"] == "550 mailbox não existe"


def test_relatorio_entrega_dedupe_por_decisor_mantem_bounce_mais_recente(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    conta, decisor = criar_conta_com_decisor()
    antiga = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi 1", StubPlanLimitsProvider(),
    )
    antiga.status = "enviado"
    antiga.bounce_em = datetime(2026, 1, 1, tzinfo=UTC)
    antiga.motivo_bounce = "bounce antigo"
    recente = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi 2", StubPlanLimitsProvider(),
    )
    recente.status = "enviado"
    recente.bounce_em = datetime(2026, 6, 1, tzinfo=UTC)
    recente.motivo_bounce = "bounce recente"
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega").json()

    assert len(corpo["contatos_com_bounce"]) == 1
    assert corpo["contatos_com_bounce"][0]["motivo_bounce"] == "bounce recente"


def test_suprimir_decisor_cancela_mensagens_pendentes(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    conta, decisor = criar_conta_com_decisor()
    pendente = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi", StubPlanLimitsProvider(),
    )
    pendente.status = "aprovado"
    db_session.commit()

    resposta = client.post(f"/api/v1/contas/{conta.id}/decisores/{decisor.id}/suprimir")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["suprimido"] is True
    assert corpo["mensagens_canceladas"] == 1
    db_session.refresh(pendente)
    assert pendente.status == "cancelado"
