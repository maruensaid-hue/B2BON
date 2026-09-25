TENANT_B = "tenant-outro"


def _conectar_e_abrir_sala(client, headers_b):
    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_b)
    return client.post("/api/v1/rede-social/salas", json={"tenant_id_alvo": TENANT_B}).json()


def _criar_negocio_via_api(client) -> int:
    conta = client.post("/api/v1/leads/contas", json={"nome": "Conta Teste"}).json()
    decisor = client.post(
        f"/api/v1/contas/{conta['id']}/decisores", json={"nome": "Decisor Teste"}
    ).json()
    negocio = client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta["id"], "decisor_id": decisor["id"], "nome": "Negócio via API", "valor": 5000},
    ).json()
    return negocio["id"]


def test_vincular_e_obter_negocio_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    sala = _conectar_e_abrir_sala(client, headers_b)
    negocio_id = _criar_negocio_via_api(client)

    resposta = client.post(
        f"/api/v1/rede-social/salas/{sala['id']}/negocio", json={"negocio_id": negocio_id, "visivel_para_comprador": True}
    )
    assert resposta.status_code == 201

    visto_pelo_comprador = client.get(f"/api/v1/rede-social/salas/{sala['id']}/negocio", headers=headers_b).json()
    assert visto_pelo_comprador is not None
    # Fase 11: o comprador não vê o nome interno do negócio, só o título compartilhado.
    assert visto_pelo_comprador["negocio_nome"] is None and visto_pelo_comprador["estagio_nome"] is None
    assert visto_pelo_comprador["titulo_compartilhado"] == "Proposta em andamento"


def test_canal_interno_via_api_nao_aparece_pro_outro_lado(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    sala = _conectar_e_abrir_sala(client, headers_b)

    canal = client.post(
        f"/api/v1/rede-social/salas/{sala['id']}/canais", json={"tipo": "LEGAL", "escopo": "interno"}
    ).json()
    assert canal["escopo"] == "interno"

    canais_de_b = client.get(f"/api/v1/rede-social/salas/{sala['id']}/canais", headers=headers_b).json()
    assert not any(c["id"] == canal["id"] for c in canais_de_b)
