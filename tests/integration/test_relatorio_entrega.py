from datetime import UTC, datetime

from app.models.campanha import Campanha, CampanhaDestinatario
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


def test_envios_email_classifica_cada_mensagem_individualmente(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    """Raio-X 2026-09-17 — o cliente via só '2 entregas' (uma por
    cadência) no KPI agregado; este endpoint mostra cada destinatário
    individualmente com o status real."""
    conta, decisor = criar_conta_com_decisor()

    enviada = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi", StubPlanLimitsProvider(),
    )
    enviada.status = "enviado"

    aberta = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi 2", StubPlanLimitsProvider(),
    )
    aberta.status = "enviado"
    aberta.aberto_em = datetime.now(UTC)

    com_erro = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi 3", StubPlanLimitsProvider(),
    )
    com_erro.status = "enviado"
    com_erro.bounce_em = datetime.now(UTC)
    com_erro.motivo_bounce = "550 mailbox não existe"

    pendente = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi 4", StubPlanLimitsProvider(),
    )
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega/envios").json()

    assert corpo["total"] == 4
    assert corpo["contagem_por_status"] == {"enviado": 1, "aberto": 1, "erro": 1, "pendente": 1}
    item_erro = next(item for item in corpo["itens"] if item["status"] == "erro")
    assert item_erro["detalhe"] == "550 mailbox não existe"
    assert item_erro["decisor_id"] == decisor.id


def test_envios_email_filtra_por_status(client, onboarding_completo, criar_conta_com_decisor, db_session):
    conta, decisor = criar_conta_com_decisor()
    com_erro = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi", StubPlanLimitsProvider(),
    )
    com_erro.status = "enviado"
    com_erro.bounce_em = datetime.now(UTC)
    com_erro.motivo_bounce = "erro"
    ok = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi 2", StubPlanLimitsProvider(),
    )
    ok.status = "enviado"
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega/envios?status=erro").json()

    assert corpo["total"] == 1
    assert corpo["itens"][0]["status"] == "erro"
    # `contagem_por_status` sempre reflete o total, independente do filtro.
    assert corpo["contagem_por_status"] == {"erro": 1, "enviado": 1}


def test_envios_email_de_campanha_so_conta_quando_canal_email_esta_ativo(
    client, onboarding_completo, db_session
):
    campanha_so_whatsapp = Campanha(tenant_id=TENANT_ID, nome="Campanha WhatsApp", tipo="marketing", canais=["whatsapp"])
    db_session.add(campanha_so_whatsapp)
    db_session.flush()
    db_session.add(
        CampanhaDestinatario(
            tenant_id=TENANT_ID, campanha_id=campanha_so_whatsapp.id, nome="Fulano",
            email="fulano@teste.com", telefone="+5511999999999", status="enviado",
        )
    )

    campanha_email = Campanha(tenant_id=TENANT_ID, nome="Campanha E-mail", tipo="marketing", canais=["email"])
    db_session.add(campanha_email)
    db_session.flush()
    db_session.add(
        CampanhaDestinatario(
            tenant_id=TENANT_ID, campanha_id=campanha_email.id, nome="Ciclano", email="ciclano@teste.com", status="enviado",
        )
    )
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega/envios").json()

    assert corpo["total"] == 1
    assert corpo["itens"][0]["nome"] == "Ciclano"
    assert corpo["itens"][0]["origem"] == "campanha"
    assert corpo["itens"][0]["origem_nome"] == "Campanha E-mail"
