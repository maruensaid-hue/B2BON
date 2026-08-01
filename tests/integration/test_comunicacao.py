def _configurar_comunicacao(client, restricoes=None):
    resposta = client.put(
        "/api/v1/comunicacao",
        json={"tom": "consultivo", "restricoes": restricoes or []},
    )
    assert resposta.status_code == 200
    return resposta.json()


def test_validar_texto_bloqueia_frase_restrita(client):
    """E1-H3: lista de restrições bloqueia geração que as viole."""
    _configurar_comunicacao(client, restricoes=["garantimos resultado"])

    resposta = client.post(
        "/api/v1/comunicacao/validar-texto",
        json={"texto": "Garantimos resultado em 30 dias."},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["valido"] is False
    assert "garantimos resultado" in corpo["violacoes"]


def test_amostra_retorna_tres_mensagens_compliant(client, criar_icp, criar_oferta, fake_llm):
    """E1-H3: usuário vê 3 mensagens de exemplo antes de ativar o motor."""
    criar_icp()
    criar_oferta()
    _configurar_comunicacao(client, restricoes=["garantimos resultado"])

    resposta = client.post("/api/v1/comunicacao/amostra")

    assert resposta.status_code == 200
    mensagens = resposta.json()["mensagens"]
    assert len(mensagens) == 3
    for mensagem in mensagens:
        assert "garantimos resultado" not in mensagem.lower()


def test_amostra_falha_quando_llm_so_gera_texto_violador(client, criar_icp, criar_oferta, fake_llm):
    criar_icp()
    criar_oferta()
    _configurar_comunicacao(client, restricoes=["garantimos resultado"])
    fake_llm.definir_respostas(["Garantimos resultado sempre."] * 10)

    resposta = client.post("/api/v1/comunicacao/amostra")

    assert resposta.status_code == 409


def test_amostra_sem_icp_ativo_e_bloqueada(client, criar_oferta):
    criar_oferta()
    _configurar_comunicacao(client)

    resposta = client.post("/api/v1/comunicacao/amostra")

    assert resposta.status_code == 409
