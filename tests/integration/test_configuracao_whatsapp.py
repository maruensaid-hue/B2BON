from app.models.configuracao_whatsapp import ConfiguracaoWhatsApp

TENANT_ID = "tenant-teste"


def test_obter_configuracao_whatsapp_sem_configuracao_retorna_none(client):
    resposta = client.get("/api/v1/configuracao-whatsapp")

    assert resposta.status_code == 200
    assert resposta.json() is None


def test_salvar_configuracao_whatsapp_sem_token_na_primeira_vez_falha(client):
    resposta = client.put(
        "/api/v1/configuracao-whatsapp",
        json={"phone_number_id": "123", "business_account_id": "456"},
    )

    assert resposta.status_code == 422


def test_salvar_configuracao_whatsapp_cria_e_mascara_token(client, db_session):
    resposta = client.put(
        "/api/v1/configuracao-whatsapp",
        json={"phone_number_id": "123", "business_account_id": "456", "access_token": "segredo-super-longo"},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["phone_number_id"] == "123"
    assert corpo["business_account_id"] == "456"
    assert corpo["access_token_mascarado"].endswith("ongo")
    assert "segredo-super-longo" not in corpo["access_token_mascarado"]

    config = db_session.query(ConfiguracaoWhatsApp).filter_by(tenant_id=TENANT_ID).one()
    assert config.access_token == "segredo-super-longo"


def test_obter_configuracao_whatsapp_apos_salvar_nunca_expoe_token_puro(client):
    client.put(
        "/api/v1/configuracao-whatsapp",
        json={"phone_number_id": "123", "business_account_id": "456", "access_token": "segredo-super-longo"},
    )

    resposta = client.get("/api/v1/configuracao-whatsapp")

    assert resposta.status_code == 200
    assert "segredo-super-longo" not in resposta.text


def test_salvar_configuracao_whatsapp_sem_reenviar_token_mantem_o_existente(client, db_session):
    client.put(
        "/api/v1/configuracao-whatsapp",
        json={"phone_number_id": "123", "business_account_id": "456", "access_token": "token-original"},
    )

    resposta = client.put(
        "/api/v1/configuracao-whatsapp",
        json={"phone_number_id": "999", "business_account_id": "456"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["phone_number_id"] == "999"
    config = db_session.query(ConfiguracaoWhatsApp).filter_by(tenant_id=TENANT_ID).one()
    assert config.access_token == "token-original"


def test_configuracao_whatsapp_bloqueada_para_papel_user(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="user-comum@teste.com.br")

    resposta_get = client.get("/api/v1/configuracao-whatsapp", headers=headers_user)
    resposta_put = client.put(
        "/api/v1/configuracao-whatsapp",
        json={"phone_number_id": "123", "business_account_id": "456", "access_token": "token"},
        headers=headers_user,
    )

    assert resposta_get.status_code == 403
    assert resposta_put.status_code == 403
