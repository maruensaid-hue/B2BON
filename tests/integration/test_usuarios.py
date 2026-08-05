TENANT_ID = "tenant-teste"


def test_admin_lista_usuarios_do_tenant(client, criar_usuario_autenticado):
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="gestor-lista@teste.com.br")
    criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-lista@teste.com.br")

    resposta = client.get("/api/v1/usuarios", headers=headers_admin)

    assert resposta.status_code == 200
    emails = {u["email"] for u in resposta.json()}
    assert "gestor-lista@teste.com.br" in emails
    assert "vendedor-lista@teste.com.br" in emails


def test_user_comum_nao_acessa_lista_de_usuarios(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="sem-acesso@teste.com.br")

    resposta = client.get("/api/v1/usuarios", headers=headers_user)

    assert resposta.status_code == 403
