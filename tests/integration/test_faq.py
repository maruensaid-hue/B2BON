TENANT_ID = "tenant-teste"


def _responder_whatsapp(client, decisor, texto):
    return client.post(
        "/api/v1/webhooks/whatsapp", json={"tenant_id": TENANT_ID, "telefone": decisor.telefone, "texto": texto}
    )


def _criar_faq(client, pergunta: str, resposta: str) -> dict:
    resposta_criacao = client.post("/api/v1/faq", json={"pergunta": pergunta, "resposta": resposta})
    assert resposta_criacao.status_code == 201, resposta_criacao.text
    return resposta_criacao.json()


def test_faq_responde_com_texto_armazenado_sem_transferir(client, criar_conta_com_decisor, fake_llm):
    """E5-H4: FAQ automática nunca inventa resposta — usa o texto armazenado na base."""
    _criar_faq(client, "Qual o prazo de implantação?", "O prazo médio de implantação é de 4 semanas.")
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["FAQ: 1"])

    resposta = _responder_whatsapp(client, decisor, "Qual o prazo de implantação de vocês?")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["faq_respondida"] is True
    assert corpo["transferido"] is False

    conversa_id = corpo["conversa_id"]
    detalhe = client.get(f"/api/v1/conversas/{conversa_id}").json()
    saida = [t for t in detalhe["turnos"] if t["direcao"] == "saida"]
    assert saida[0]["conteudo"] == "O prazo médio de implantação é de 4 semanas."


def test_faq_nao_avanca_etapa_do_roteiro(client, criar_conta_com_decisor, fake_llm):
    _criar_faq(client, "Vocês atendem qual segmento?", "Atendemos PMEs de tecnologia e serviços.")
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["FAQ: 1"])

    corpo = _responder_whatsapp(client, decisor, "Vocês atendem qual segmento?").json()

    assert corpo["etapa_atual"] == "dores"  # roteiro pausado no mesmo ponto


def test_pergunta_fora_da_base_transfere_nunca_inventa(client, criar_conta_com_decisor, fake_llm):
    """E5-H4: pergunta fora da base gera transferência, nunca resposta inventada."""
    _criar_faq(client, "Qual o prazo de implantação?", "O prazo médio de implantação é de 4 semanas.")
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["FAQ: 99"])  # índice fora da base carregada

    resposta = _responder_whatsapp(client, decisor, "Pergunta totalmente aleatória")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["transferido"] is True
    assert corpo["status"] == "transferida_humano"
    assert corpo["faq_respondida"] is False


def test_sem_faq_cadastrada_prefixo_faq_tambem_transfere(client, criar_conta_com_decisor, fake_llm):
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["FAQ: 1"])  # nenhuma FAQ cadastrada — índice inválido

    corpo = _responder_whatsapp(client, decisor, "Alguma pergunta").json()

    assert corpo["transferido"] is True


def test_faq_perguntar_responde_com_ia(client, fake_llm):
    """Raio-X 2026-09-01: FAQ interativa com IA, distinta da FAQ curada
    por tenant testada acima — qualquer usuário autenticado pode
    perguntar livremente sobre como usar a plataforma."""
    fake_llm.definir_respostas(["Vai em Configuração e cadastra seu SMTP próprio."])

    resposta = client.post("/api/v1/faq/perguntar", json={"pergunta": "Como configuro o e-mail?"})

    assert resposta.status_code == 200
    assert resposta.json() == {"resposta": "Vai em Configuração e cadastra seu SMTP próprio."}


def test_faq_perguntar_sem_autenticacao_recusa(client):
    resposta = client.post("/api/v1/faq/perguntar", json={"pergunta": "Oi"}, headers={"Authorization": ""})

    assert resposta.status_code == 401
