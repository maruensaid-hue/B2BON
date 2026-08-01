def _registrar_tratamento(client, tipo="prospeccao_whatsapp", dados_tratados=None):
    return client.post(
        "/api/v1/ropa",
        json={
            "tipo_tratamento": tipo,
            "finalidade": "Prospecção B2B via WhatsApp sob legítimo interesse.",
            "dados_tratados": dados_tratados or ["nome", "cargo", "telefone"],
            "balanceamento_documentado": "Teste de balanceamento de legítimo interesse.",
        },
    )


def test_ropa_plataforma_versionado(client):
    """E9-H1: ROPA de plataforma, versionado, operações padrão do módulo."""
    primeira = _registrar_tratamento(client)
    assert primeira.status_code == 201
    assert primeira.json()["versao"] == 1

    segunda = _registrar_tratamento(client, dados_tratados=["nome", "cargo", "telefone", "email"])
    assert segunda.json()["versao"] == 2

    ativos = client.get("/api/v1/ropa").json()
    assert len(ativos) == 1  # só a versão mais recente fica ativa
    assert ativos[0]["versao"] == 2


def test_ropa_tenant_gerado_automaticamente(client, criar_icp):
    """E9-H1: registro por tenant gerado automaticamente da configuração do assinante."""
    icp = criar_icp()

    resposta = client.get("/api/v1/ropa/tenant")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tenant_id"] == "tenant-teste"
    assert corpo["icp_ids"] == [icp["id"]]
    assert corpo["base_legal"] == "legitimo_interesse"


def test_minimizacao_verificada(client, criar_icp):
    """E9-H1: minimização verificada — motor não coleta dados além do necessário."""
    criar_icp()

    resposta = client.get("/api/v1/ropa/minimizacao")

    assert resposta.status_code == 200
    assert resposta.json() == {"conforme": True, "divergencias": []}
