"""D-086: tema claro/escuro é preferência do USUÁRIO — persiste no servidor e volta em /auth/eu (e no login)."""


def test_tema_padrao_e_nulo_e_a_escolha_persiste(client):
    assert client.get("/api/v1/auth/eu").json()["tema_preferido"] is None

    resposta = client.put("/api/v1/auth/preferencia-tema", json={"tema": "dark"})
    assert resposta.status_code == 200 and resposta.json()["tema_preferido"] == "dark"
    assert client.get("/api/v1/auth/eu").json()["tema_preferido"] == "dark"
    # a resposta é o usuário completo (não apaga recursos do plano da sessão)
    assert "recursos_plano" in resposta.json()

    assert client.put("/api/v1/auth/preferencia-tema", json={"tema": "light"}).json()["tema_preferido"] == "light"


def test_tema_invalido_e_recusado(client):
    assert client.put("/api/v1/auth/preferencia-tema", json={"tema": "azul"}).status_code == 422


def test_tema_exige_login(client):
    assert client.put("/api/v1/auth/preferencia-tema", json={"tema": "dark"}, headers={"Authorization": ""}).status_code == 401
