TENANT_B = "tenant-outro"


def _conectar_via_api(client, headers_b):
    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_b)


def test_abrir_sala_e_listar_canais_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _conectar_via_api(client, headers_b)

    resposta = client.post("/api/v1/rede-social/salas", json={"tenant_id_alvo": TENANT_B})
    assert resposta.status_code == 201
    sala = resposta.json()

    canais = client.get(f"/api/v1/rede-social/salas/{sala['id']}/canais").json()
    assert len(canais) == 1
    assert canais[0]["tipo"] == "GENERAL"

    salas_de_b = client.get("/api/v1/rede-social/salas", headers=headers_b).json()
    assert len(salas_de_b) == 1
    assert salas_de_b[0]["tenant_id_alvo"] == "tenant-teste"


def test_abrir_sala_sem_conexao_retorna_erro_de_negocio(client):
    resposta = client.post("/api/v1/rede-social/salas", json={"tenant_id_alvo": TENANT_B})

    assert resposta.status_code == 409


def test_criar_canal_e_trocar_mensagens_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _conectar_via_api(client, headers_b)
    sala = client.post("/api/v1/rede-social/salas", json={"tenant_id_alvo": TENANT_B}).json()

    canal = client.post(
        f"/api/v1/rede-social/salas/{sala['id']}/canais", json={"tipo": "COMMERCIAL"}
    ).json()
    assert canal["tipo"] == "COMMERCIAL"

    resposta_msg = client.post(
        f"/api/v1/rede-social/salas/canais/{canal['id']}/mensagens", json={"texto": "Olá, tudo bem?"}
    )
    assert resposta_msg.status_code == 201

    mensagens_vistas_por_b = client.get(
        f"/api/v1/rede-social/salas/canais/{canal['id']}/mensagens", headers=headers_b
    ).json()
    assert len(mensagens_vistas_por_b) == 1
    assert mensagens_vistas_por_b[0]["texto"] == "Olá, tudo bem?"

    notificacoes_b = client.get("/api/v1/rede-social/notificacoes", headers=headers_b).json()
    assert any(n["tipo"] == "sala_mensagem" for n in notificacoes_b)


def test_tenant_de_fora_recebe_403_ao_acessar_sala(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _conectar_via_api(client, headers_b)
    sala = client.post("/api/v1/rede-social/salas", json={"tenant_id_alvo": TENANT_B}).json()

    headers_c = criar_usuario_autenticado("tenant-terceiro", papel="admin", email="admin@terceiro.com.br")
    resposta = client.get(f"/api/v1/rede-social/salas/{sala['id']}/canais", headers=headers_c)

    assert resposta.status_code == 403
