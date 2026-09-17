TENANT_B = "tenant-outro"

_INTENT_PAYLOAD = {
    "categoria": "backup",
    "titulo": "Backup imutável para 500 endpoints",
    "descricao": "Procuramos solução de backup imutável resistente a ransomware.",
    "requisitos": ["imutabilidade"],
    "visibilidade": "publica",
}


def test_listar_matches_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "produtos_servicos": ["backup imutável"]},
        headers=headers_b,
    )
    intent = client.post("/api/v1/rede-social/intents", json=_INTENT_PAYLOAD).json()

    resposta = client.get(f"/api/v1/inteligencia-rede/intents/{intent['id']}/matches")

    assert resposta.status_code == 200
    matches = resposta.json()
    assert len(matches) == 1
    assert matches[0]["tenant_id_candidato"] == TENANT_B


def test_matches_de_intent_inexistente_retorna_404(client):
    resposta = client.get("/api/v1/inteligencia-rede/intents/9999/matches")

    assert resposta.status_code == 404


def test_explicar_match_com_ia_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "produtos_servicos": ["backup imutável"]},
        headers=headers_b,
    )
    intent = client.post("/api/v1/rede-social/intents", json=_INTENT_PAYLOAD).json()

    resposta = client.post(f"/api/v1/inteligencia-rede/intents/{intent['id']}/matches/{TENANT_B}/explicar-com-ia")

    assert resposta.status_code == 200
    assert "explicacao" in resposta.json()
