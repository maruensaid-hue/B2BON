from sqlalchemy import text

from app.models.configuracao_email_smtp import ConfiguracaoEmailSmtp

TENANT_ID = "tenant-teste"

_PAYLOAD_PADRAO = {"host": "smtp.gmail.com", "porta": 587, "usuario": "contato@empresa.com.br", "usar_tls": True}


def test_obter_configuracao_email_smtp_sem_configuracao_retorna_none(client):
    resposta = client.get("/api/v1/configuracao-email-smtp")

    assert resposta.status_code == 200
    assert resposta.json() is None


def test_salvar_configuracao_email_smtp_sem_senha_na_primeira_vez_falha(client):
    resposta = client.put("/api/v1/configuracao-email-smtp", json=_PAYLOAD_PADRAO)

    assert resposta.status_code == 422


def test_salvar_configuracao_email_smtp_cria_e_mascara_senha(client, db_session):
    resposta = client.put(
        "/api/v1/configuracao-email-smtp", json={**_PAYLOAD_PADRAO, "senha": "segredo-super-longo"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["host"] == "smtp.gmail.com"
    assert corpo["porta"] == 587
    assert corpo["usuario"] == "contato@empresa.com.br"
    assert corpo["senha_mascarada"].endswith("ongo")
    assert "segredo-super-longo" not in corpo["senha_mascarada"]

    config = db_session.query(ConfiguracaoEmailSmtp).filter_by(tenant_id=TENANT_ID).one()
    assert config.senha == "segredo-super-longo"


def test_salvar_configuracao_email_smtp_criptografa_credenciais_no_banco(client, db_session):
    client.put("/api/v1/configuracao-email-smtp", json={**_PAYLOAD_PADRAO, "senha": "segredo-super-longo"})

    linha_crua = db_session.execute(
        text("SELECT usuario, senha FROM configuracao_email_smtp WHERE tenant_id = :tenant_id"),
        {"tenant_id": TENANT_ID},
    ).one()

    assert linha_crua.usuario != "contato@empresa.com.br"
    assert linha_crua.senha != "segredo-super-longo"

    config = db_session.query(ConfiguracaoEmailSmtp).filter_by(tenant_id=TENANT_ID).one()
    assert config.usuario == "contato@empresa.com.br"
    assert config.senha == "segredo-super-longo"


def test_obter_configuracao_email_smtp_apos_salvar_nunca_expoe_senha_pura(client):
    client.put("/api/v1/configuracao-email-smtp", json={**_PAYLOAD_PADRAO, "senha": "segredo-super-longo"})

    resposta = client.get("/api/v1/configuracao-email-smtp")

    assert resposta.status_code == 200
    assert "segredo-super-longo" not in resposta.text


def test_salvar_configuracao_email_smtp_sem_reenviar_senha_mantem_a_existente(client, db_session):
    client.put("/api/v1/configuracao-email-smtp", json={**_PAYLOAD_PADRAO, "senha": "senha-original"})

    resposta = client.put(
        "/api/v1/configuracao-email-smtp",
        json={"host": "smtp.outro.com", "porta": 465, "usuario": "novo@empresa.com.br", "usar_tls": False},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["host"] == "smtp.outro.com"
    assert corpo["usar_tls"] is False
    config = db_session.query(ConfiguracaoEmailSmtp).filter_by(tenant_id=TENANT_ID).one()
    assert config.senha == "senha-original"


def test_salvar_configuracao_email_smtp_sobrescreve_senha_indecifravel(client, db_session):
    """Mesmo raio-X 2026-08-27 que corrigiu `configuracao_whatsapp.py`:
    uma senha cifrada com chave diferente da atual não pode travar o
    PUT que ia justamente sobrescrevê-la por uma nova válida."""
    db_session.execute(
        text(
            "INSERT INTO configuracao_email_smtp "
            "(tenant_id, host, porta, usuario, senha, usar_tls, criado_em, atualizado_em) "
            "VALUES (:t, 'smtp.antigo.com', 587, 'usuario-cifrado-invalido', :senha, 1, datetime('now'), datetime('now'))"
        ),
        {"t": TENANT_ID, "senha": "isto-nao-e-um-token-fernet-valido"},
    )
    db_session.commit()

    resposta = client.put(
        "/api/v1/configuracao-email-smtp",
        json={**_PAYLOAD_PADRAO, "senha": "senha-nova-valida"},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["host"] == "smtp.gmail.com"
    assert corpo["senha_mascarada"].endswith("lida")

    config = db_session.query(ConfiguracaoEmailSmtp).filter_by(tenant_id=TENANT_ID).one()
    assert config.senha == "senha-nova-valida"


def test_configuracao_email_smtp_bloqueada_para_papel_user(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="user-comum-smtp@teste.com.br")

    resposta_get = client.get("/api/v1/configuracao-email-smtp", headers=headers_user)
    resposta_put = client.put(
        "/api/v1/configuracao-email-smtp",
        json={**_PAYLOAD_PADRAO, "senha": "senha"},
        headers=headers_user,
    )

    assert resposta_get.status_code == 403
    assert resposta_put.status_code == 403
