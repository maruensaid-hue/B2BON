TENANT_ID = "tenant-teste"


def _agendar_e_realizar(client, decisor_id: int) -> dict:
    proposta = client.post(
        f"/api/v1/decisores/{decisor_id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = proposta["horarios_propostos"][0]
    confirmada = client.post(
        f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario}
    ).json()
    client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "realizada"})
    return confirmada


def test_nps_disparado_apos_marco_configuravel_de_dias(client, criar_conta_com_decisor, fake_whatsapp):
    """E11-H1: disparo de NPS configurável por marco (dias após reunião realizada)."""
    conta, decisor = criar_conta_com_decisor()
    _agendar_e_realizar(client, decisor.id)
    client.put("/api/v1/nps/configuracao", json={"dias_apos_reuniao_realizada": 0})

    resposta = client.post("/api/v1/nps/disparar-pendentes")

    assert resposta.status_code == 200
    assert resposta.json()["pesquisas_disparadas"] == 1
    assert len(fake_whatsapp.envios) == 1


def test_nps_nao_disparado_antes_do_marco_configurado(client, criar_conta_com_decisor, fake_whatsapp):
    conta, decisor = criar_conta_com_decisor()
    _agendar_e_realizar(client, decisor.id)
    client.put("/api/v1/nps/configuracao", json={"dias_apos_reuniao_realizada": 9999})

    resposta = client.post("/api/v1/nps/disparar-pendentes")

    assert resposta.json()["pesquisas_disparadas"] == 0
    assert fake_whatsapp.envios == []


def test_marco_entrega_concluida_dispara_nps_imediatamente(client, criar_conta_com_decisor, fake_whatsapp):
    """E11-H1: disparo configurável por marco — "entrega concluída"."""
    conta, decisor = criar_conta_com_decisor()

    resposta = client.post(f"/api/v1/decisores/{decisor.id}/marco-entrega")

    assert resposta.status_code == 201
    assert resposta.json()["marco"] == "entrega_concluida"
    assert len(fake_whatsapp.envios) == 1


def _obter_token_da_pesquisa(fake_whatsapp) -> str:
    texto = fake_whatsapp.envios[-1]["texto"]
    return texto.rsplit(" ", 1)[-1]


def test_classificacao_promotor_registrada_na_conta_e_no_painel(client, criar_conta_com_decisor, fake_whatsapp):
    """E11-H1: classificação promotor/neutro/detrator registrada na conta e visível no painel."""
    conta, decisor = criar_conta_com_decisor()
    client.post(f"/api/v1/decisores/{decisor.id}/marco-entrega")
    token = _obter_token_da_pesquisa(fake_whatsapp)

    resposta = client.post(f"/api/v1/nps/responder/{token}", json={"nota": 10})

    assert resposta.status_code == 200
    assert resposta.json()["classificacao"] == "promotor"

    conta_atualizada = client.get(f"/api/v1/contas/{conta.id}").json()
    assert conta_atualizada["nps_classificacao"] == "promotor"
    assert conta_atualizada["nps_nota"] == 10

    distribuicao = client.get("/api/v1/painel/nps").json()
    assert distribuicao["promotor"] == 1


def test_detrator_gera_alerta_imediato_com_sugestao(
    client, criar_conta_com_decisor, fake_whatsapp, configurar_notificacao
):
    """E11-H1: detrator gera alerta imediato ao Gestor Comercial com sugestão de ação."""
    configurar_notificacao()
    conta, decisor = criar_conta_com_decisor()
    client.post(f"/api/v1/decisores/{decisor.id}/marco-entrega")
    token = _obter_token_da_pesquisa(fake_whatsapp)
    envios_antes = len(fake_whatsapp.envios)

    resposta = client.post(f"/api/v1/nps/responder/{token}", json={"nota": 2})

    assert resposta.json()["classificacao"] == "detrator"
    distribuicao = client.get("/api/v1/painel/nps").json()
    assert distribuicao["detrator"] == 1
    assert len(fake_whatsapp.envios) == envios_antes + 1  # alerta ao vendedor

    eventos = {e["evento_tipo"] for e in client.get("/api/v1/auditoria").json()}
    assert "alerta_detrator_criado" in eventos


def test_neutro_nao_gera_alerta_nem_indicacao(client, criar_conta_com_decisor, fake_whatsapp):
    conta, decisor = criar_conta_com_decisor()
    client.post(f"/api/v1/decisores/{decisor.id}/marco-entrega")
    token = _obter_token_da_pesquisa(fake_whatsapp)

    corpo = client.post(f"/api/v1/nps/responder/{token}", json={"nota": 7}).json()

    assert corpo["classificacao"] == "neutro"
    assert client.get("/api/v1/indicacoes").json() == []
