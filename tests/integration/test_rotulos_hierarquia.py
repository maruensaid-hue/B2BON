def test_lista_rotulos_e_publica_com_os_padroes(client):
    resposta = client.get("/api/v1/rotulos-hierarquia", headers={"Authorization": ""})

    assert resposta.status_code == 200
    corpo = {item["tipo"]: item["rotulo"] for item in resposta.json()}
    assert corpo == {"distribuidor": "Master", "revendedor": "Vendedor", "cliente": "Cliente"}


def test_super_admin_atualiza_os_rotulos(client):
    resposta = client.put(
        "/api/v1/rotulos-hierarquia",
        json={"rotulo_distribuidor": "Franqueadora", "rotulo_revendedor": "Franqueado", "rotulo_cliente": "Consumidor"},
    )

    assert resposta.status_code == 200
    corpo = {item["tipo"]: item["rotulo"] for item in resposta.json()}
    assert corpo == {"distribuidor": "Franqueadora", "revendedor": "Franqueado", "cliente": "Consumidor"}

    lista = client.get("/api/v1/rotulos-hierarquia", headers={"Authorization": ""}).json()
    assert {item["tipo"]: item["rotulo"] for item in lista} == corpo


def test_usuario_comum_nao_pode_atualizar_rotulos(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado("outro-tenant", papel="admin")

    resposta = client.put(
        "/api/v1/rotulos-hierarquia",
        json={"rotulo_distribuidor": "X", "rotulo_revendedor": "Y", "rotulo_cliente": "Z"},
        headers=headers,
    )

    assert resposta.status_code == 403


def test_atualizar_com_rotulo_vazio_recusa(client):
    resposta = client.put(
        "/api/v1/rotulos-hierarquia",
        json={"rotulo_distribuidor": "Master", "rotulo_revendedor": "  ", "rotulo_cliente": "Cliente"},
    )

    assert resposta.status_code == 422
