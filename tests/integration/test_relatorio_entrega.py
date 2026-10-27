from datetime import UTC, datetime, timedelta

from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.configuracao_email_smtp import ConfiguracaoEmailSmtp
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

    aprovacao_service.criar_proposta(
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


def test_envios_email_pendente_explica_quando_canal_esta_pausado(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    """Incidente 2026-10-05: 22 mensagens aprovadas ficavam "Pendente" sem
    nenhum motivo enquanto o canal estava pausado."""
    from app.services import reputacao_service

    conta, decisor = criar_conta_com_decisor()
    mensagem = aprovacao_service.criar_proposta(
        db_session, TENANT_ID, None, decisor.id, "email", None, "Oi", StubPlanLimitsProvider(),
    )
    mensagem.status = "aprovado"
    db_session.commit()

    sem_pausa = client.get("/api/v1/relatorio-entrega/envios").json()["itens"][0]
    assert sem_pausa["status"] == "pendente"
    assert sem_pausa["detalhe"] is None

    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 6)

    pausado = client.get("/api/v1/relatorio-entrega/envios").json()["itens"][0]
    assert pausado["status"] == "pendente"
    assert pausado["detalhe"] == "Aguardando — canal de e-mail pausado"


def _campanha_email(db_session) -> Campanha:
    campanha = Campanha(tenant_id=TENANT_ID, nome="Campanha E-mail", tipo="marketing", canais=["email"])
    db_session.add(campanha)
    db_session.flush()
    return campanha


def test_envios_de_campanha_classificam_cada_status_inclusive_nao_enviado(client, onboarding_completo, db_session):
    campanha = _campanha_email(db_session)
    for nome, status, motivo in [
        ("Enviado", "enviado", None),
        ("Falhou", "falhou", "550 caixa inexistente"),
        ("Sem email", "nao_enviado", "E-mail inválido: https://www.linkedin.com/in/fulano"),
        ("Adiado", "pendente", "Envio adiado, nova tentativa automática em breve."),
        ("Retido", "retido", None),
        ("Saiu", "optout", None),
    ]:
        db_session.add(
            CampanhaDestinatario(
                tenant_id=TENANT_ID, campanha_id=campanha.id, nome=nome, email=f"{nome.replace(' ', '').lower()}@teste.com",
                status=status, motivo_falha=motivo, empresa="Acme" if nome == "Enviado" else None,
            )
        )
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega/envios").json()

    por_nome = {item["nome"]: item for item in corpo["itens"]}
    assert por_nome["Enviado"]["status"] == "enviado" and por_nome["Enviado"]["conta_nome"] == "Acme"
    assert por_nome["Falhou"]["status"] == "erro" and por_nome["Falhou"]["detalhe"] == "550 caixa inexistente"
    assert por_nome["Sem email"]["status"] == "nao_enviado"  # antes caía em "enviado"
    assert por_nome["Sem email"]["detalhe"].startswith("E-mail inválido")
    assert por_nome["Adiado"]["status"] == "pendente" and "nova tentativa" in por_nome["Adiado"]["detalhe"]
    assert por_nome["Retido"]["status"] == "pendente"
    assert por_nome["Saiu"]["status"] == "cancelado"
    assert corpo["contagem_por_status"] == {"enviado": 1, "erro": 1, "nao_enviado": 1, "pendente": 2, "cancelado": 1}

    so_nao_enviados = client.get("/api/v1/relatorio-entrega/envios", params={"status": "nao_enviado"}).json()
    assert [item["nome"] for item in so_nao_enviados["itens"]] == ["Sem email"]


def test_resumo_conta_os_envios_reais_dos_ultimos_7_dias_mesmo_sem_retorno_do_provedor(client, onboarding_completo, db_session):
    campanha = _campanha_email(db_session)
    agora = datetime.now(UTC)
    antigo = agora - timedelta(days=10)
    for nome, status, quando in [
        ("A", "enviado", agora), ("B", "enviado", agora), ("C", "falhou", agora), ("D", "nao_enviado", agora), ("E", "pendente", agora),
        ("Velho", "enviado", antigo),
    ]:
        db_session.add(
            CampanhaDestinatario(
                tenant_id=TENANT_ID, campanha_id=campanha.id, nome=nome, email=f"{nome.lower()}@teste.com", status=status,
                enviado_em=quando if status == "enviado" else None, criado_em=quando,
            )
        )
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega").json()

    assert corpo["resumo_envios"] == {"enviados": 2, "erros": 1, "nao_enviados": 1, "pendentes": 1}
    assert corpo["saude_email"]["enviados"] == 0  # o contador de reputação só conhece o retorno do provedor
    assert corpo["saude_email"]["medido_pelo_provedor"] is True  # sem conta SMTP própria, o provedor da plataforma devolve bounce


def test_com_conta_smtp_propria_o_relatorio_avisa_que_bounce_e_spam_nao_sao_medidos(client, onboarding_completo, db_session):
    db_session.add(ConfiguracaoEmailSmtp(tenant_id=TENANT_ID, host="smtp.gmail.com", porta=587, usuario="eu@teste.com", senha="senha-de-app", usar_tls=True))
    db_session.commit()

    corpo = client.get("/api/v1/relatorio-entrega").json()

    assert corpo["saude_email"]["medido_pelo_provedor"] is False


def test_registrar_bounces_manuais_marca_campanha_e_cadencia_e_informa_o_que_nao_achou(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    campanha = _campanha_email(db_session)
    for nome, email in [("Maria", "maria@teste.com"), ("Joao", "joao@teste.com"), ("Ana", "ana@teste.com")]:
        db_session.add(CampanhaDestinatario(tenant_id=TENANT_ID, campanha_id=campanha.id, nome=nome, email=email, status="enviado"))
    conta, decisor = criar_conta_com_decisor()
    mensagem = aprovacao_service.criar_proposta(db_session, TENANT_ID, None, decisor.id, "email", None, "Oi", StubPlanLimitsProvider())
    mensagem.status = "enviado"
    db_session.commit()

    resposta = client.post(
        "/api/v1/relatorio-entrega/bounces-manuais",
        json={
            "texto": f"MARIA@teste.com, joao@teste.com;\nAddress not found: {decisor.email}\nmailer-daemon@googlemail.com maria@teste.com"
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert sorted(corpo["registrados"]) == sorted(["maria@teste.com", "joao@teste.com", decisor.email.lower()])  # sem repetir, sem diferenciar maiúsculas
    assert corpo["nao_encontrados"] == ["mailer-daemon@googlemail.com"]
    assert corpo["ja_registrados"] == []

    erros = client.get("/api/v1/relatorio-entrega/envios", params={"status": "erro"}).json()
    assert sorted(item["email"] for item in erros["itens"]) == sorted(["maria@teste.com", "joao@teste.com", decisor.email])
    assert all("Informado manualmente" in item["detalhe"] for item in erros["itens"])
    assert [i["nome"] for i in client.get("/api/v1/relatorio-entrega/envios", params={"status": "enviado"}).json()["itens"]] == ["Ana"]
    assert client.get("/api/v1/relatorio-entrega").json()["saude_email"]["pausado"] is False  # não mexe na reputação do canal

    de_novo = client.post("/api/v1/relatorio-entrega/bounces-manuais", json={"texto": "maria@teste.com"}).json()
    assert de_novo["registrados"] == [] and de_novo["ja_registrados"] == ["maria@teste.com"]


def test_registrar_bounces_manuais_sem_endereco_e_recusado(client, onboarding_completo):
    resposta = client.post("/api/v1/relatorio-entrega/bounces-manuais", json={"texto": "  sem nenhum endereço aqui  "})

    assert resposta.status_code == 422


def test_registrar_bounces_manuais_so_enxerga_os_envios_do_proprio_tenant(client, onboarding_completo, db_session):
    campanha = Campanha(tenant_id="outro-tenant", nome="De outro", tipo="marketing", canais=["email"])
    db_session.add(campanha)
    db_session.flush()
    db_session.add(CampanhaDestinatario(tenant_id="outro-tenant", campanha_id=campanha.id, nome="X", email="x@teste.com", status="enviado"))
    db_session.commit()

    corpo = client.post("/api/v1/relatorio-entrega/bounces-manuais", json={"texto": "x@teste.com"}).json()

    assert corpo["registrados"] == [] and corpo["nao_encontrados"] == ["x@teste.com"]
