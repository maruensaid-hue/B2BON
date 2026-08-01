TENANT_ID = "tenant-teste"


def _responder_whatsapp(client, decisor, texto):
    return client.post(
        "/api/v1/webhooks/whatsapp", json={"tenant_id": TENANT_ID, "telefone": decisor.telefone, "texto": texto}
    )


def test_roteiro_avanca_etapas_adaptativamente(client, criar_conta_com_decisor, fake_llm):
    """E5-H1: roteiro de qualificação S.H.A.R.K. adaptativo às respostas."""
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["CONTINUAR: Qual é sua maior dor hoje?"])

    resposta = _responder_whatsapp(client, decisor, "Oi, tenho interesse na solução")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["transferido"] is False
    assert corpo["etapa_atual"] == "contexto"  # avançou de "dores" para "contexto"


def test_transferencia_quando_llm_nao_confirma_continuar(client, criar_conta_com_decisor, fake_llm):
    """E5-H1: detecção de intenção complexa aciona transferência imediata —
    e o requisito do usuário: sem prefixo CONTINUAR:, nunca inventa resposta."""
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["Isso parece uma reclamação, não tenho certeza do que responder."])

    resposta = _responder_whatsapp(client, decisor, "Isso é golpe? Quero cancelar tudo")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["transferido"] is True
    assert corpo["status"] == "transferida_humano"


def test_conversa_completa_na_linha_do_tempo(client, criar_conta_com_decisor, fake_llm):
    """E5-H1: conversa completa registrada na linha do tempo da conta."""
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["CONTINUAR: Qual sua maior dor?"])

    resposta = _responder_whatsapp(client, decisor, "Tenho um problema de vendas")
    conversa_id = resposta.json()["conversa_id"]

    detalhe = client.get(f"/api/v1/conversas/{conversa_id}").json()

    assert detalhe["conversa"]["decisor_id"] == decisor.id
    entrada = [t for t in detalhe["turnos"] if t["direcao"] == "entrada"]
    saida = [t for t in detalhe["turnos"] if t["direcao"] == "saida"]
    assert entrada[0]["conteudo"] == "Tenho um problema de vendas"
    assert saida[0]["conteudo"] == "Qual sua maior dor?"


def test_limiar_configuravel_por_tenant(client):
    """E5-H2: limiar de qualificação configurável por assinante."""
    resposta = client.put("/api/v1/qualificacao/configuracao", json={"limiar_padrao": 45})

    assert resposta.status_code == 200
    assert resposta.json()["limiar_padrao"] == 45
    assert client.get("/api/v1/qualificacao/configuracao").json()["limiar_padrao"] == 45


def test_score_recalculado_a_cada_interacao(client, criar_conta_com_decisor, fake_llm):
    """E5-H2: score recalculado a cada nova interação relevante."""
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["CONTINUAR: pergunta 1", "CONTINUAR: pergunta 2"])

    primeira = _responder_whatsapp(client, decisor, "resposta 1").json()
    segunda = _responder_whatsapp(client, decisor, "resposta 2").json()

    assert segunda["score_total"] > primeira["score_total"]


def test_notifica_vendedor_ao_atingir_limiar(
    client, criar_conta_com_decisor, fake_llm, configurar_notificacao, fake_whatsapp
):
    """E5-H3: notificação em tempo real (in-app + WhatsApp do vendedor)."""
    configurar_notificacao()
    client.put("/api/v1/qualificacao/configuracao", json={"limiar_padrao": 15})
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["CONTINUAR: pergunta 1"])

    resposta = _responder_whatsapp(client, decisor, "oi").json()

    assert resposta["notificacao_id"] is not None
    notificacoes = client.get("/api/v1/notificacoes").json()
    assert len(notificacoes) == 1
    assert len(fake_whatsapp.envios) == 1


def test_notifica_vendedor_ao_transferir(client, criar_conta_com_decisor, fake_llm, configurar_notificacao):
    """E5-H3: também aciona o vendedor quando a conversa é transferida."""
    configurar_notificacao()
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["texto sem prefixo reconhecido"])

    resposta = _responder_whatsapp(client, decisor, "quero falar com um humano").json()

    assert resposta["transferido"] is True
    assert resposta["notificacao_id"] is not None


def test_sla_medido_ate_primeiro_contato(client, criar_conta_com_decisor, fake_llm, configurar_notificacao):
    """E5-H3: SLA visível — tempo entre qualificação e primeiro contato humano."""
    configurar_notificacao()
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["texto sem prefixo reconhecido"])
    resultado = _responder_whatsapp(client, decisor, "?").json()
    notificacao_id = resultado["notificacao_id"]

    antes = client.get("/api/v1/notificacoes").json()[0]
    assert antes["sla_segundos"] is None

    confirmado = client.post(f"/api/v1/notificacoes/{notificacao_id}/confirmar-contato").json()
    assert confirmado["sla_segundos"] is not None
    assert confirmado["sla_segundos"] >= 0
