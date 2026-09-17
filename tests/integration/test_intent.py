TENANT_B = "tenant-outro"

_PAYLOAD = {
    "categoria": "backup",
    "titulo": "Backup imutável",
    "descricao": "Procuramos solução de backup imutável para 500 endpoints.",
    "requisitos": ["imutabilidade"],
    "faixa_orcamento": "R$ 50k-100k",
    "localizacao": "SP",
    "visibilidade": "publica",
}


def test_criar_e_listar_intent_via_api(client):
    resposta = client.post("/api/v1/rede-social/intents", json=_PAYLOAD)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["titulo"] == "Backup imutável"
    assert corpo["status"] == "aberta"

    intents = client.get("/api/v1/rede-social/intents").json()
    assert len(intents) == 1


def test_intent_visivel_para_outro_tenant_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/intents", json=_PAYLOAD)

    intents_vistos_por_b = client.get("/api/v1/rede-social/intents", headers=headers_b).json()

    assert len(intents_vistos_por_b) == 1


def test_intent_restrita_a_conexoes_nao_aparece_para_outro_tenant(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    payload_restrita = {**_PAYLOAD, "visibilidade": "conexoes"}
    client.post("/api/v1/rede-social/intents", json=payload_restrita)

    intents_vistos_por_b = client.get("/api/v1/rede-social/intents", headers=headers_b).json()

    assert intents_vistos_por_b == []


def test_encerrar_intent_de_outro_tenant_retorna_403(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    intent = client.post("/api/v1/rede-social/intents", json=_PAYLOAD).json()

    resposta = client.post(f"/api/v1/rede-social/intents/{intent['id']}/encerrar", headers=headers_b)

    assert resposta.status_code == 403


def test_marcar_atendida_via_api(client):
    intent = client.post("/api/v1/rede-social/intents", json=_PAYLOAD).json()

    resposta = client.post(f"/api/v1/rede-social/intents/{intent['id']}/atender")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "atendida"
