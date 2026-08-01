_TOQUES_LINKEDIN_PRIMEIRO = [
    {"ordem": 1, "canal": "linkedin", "intervalo_dias_apos_anterior": 0},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 2, "template_whatsapp_id": "x"},
    {"ordem": 5, "canal": "whatsapp", "intervalo_dias_apos_anterior": 2, "template_whatsapp_id": "x"},
]


def _criar_gerar_aprovar_ativar(client, conta_id: int, toques: list[dict]) -> dict:
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência LinkedIn", "toques": toques}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    return cadencia


def test_tarefa_linkedin_tem_texto_e_link(client, onboarding_completo, criar_conta_com_decisor):
    """E3-H4: tarefa diária de LinkedIn com texto copiável e atalho para o perfil."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)

    client.post("/api/v1/envios/processar")
    tarefas = client.get("/api/v1/linkedin/tarefas").json()

    assert len(tarefas) == 1
    assert tarefas[0]["texto"]
    assert tarefas[0]["link_perfil"] == decisor.linkedin_url
    assert tarefas[0]["status"] == "pendente"


def test_linkedin_nunca_envia_automaticamente(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, fake_email
):
    """E3-H4: nenhum envio automatizado ao LinkedIn em nenhuma hipótese."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["tarefas_linkedin_criadas"] == 1
    assert resultado["enviadas"] == 0
    assert fake_whatsapp.envios == []
    assert fake_email.envios == []


def test_marcar_executada_realimenta_cadencia(client, onboarding_completo, criar_conta_com_decisor):
    """E3-H4: marcação de executado realimenta a cadência."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)
    client.post("/api/v1/envios/processar")
    tarefa = client.get("/api/v1/linkedin/tarefas").json()[0]

    resposta = client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": True})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "executada"


def test_marcar_ignorada_cancela_mensagem(client, onboarding_completo, criar_conta_com_decisor):
    """E3-H4: marcação de ignorado também realimenta a cadência."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)
    client.post("/api/v1/envios/processar")
    tarefa = client.get("/api/v1/linkedin/tarefas").json()[0]

    resposta = client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": False})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ignorada"
