from app.services import optout_service

_TOQUES_WHATSAPP_PRIMEIRO = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "x"},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 2, "template_whatsapp_id": "x"},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
]


def _criar_gerar_aprovar_ativar(client, conta_id: int, toques: list[dict]) -> dict:
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência Teste", "toques": toques}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    return cadencia


def test_optout_email_efeito_imediato_todos_canais(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    """E9-H2: opt-out via link do e-mail, efeito imediato em todos os canais."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()

    token = optout_service.gerar_token("tenant-teste", decisor.id)
    resposta = client.get(f"/api/v1/opt-out/email/{token}")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["suprimido"] is True
    assert corpo["mensagens_canceladas"] == len(itens)


def test_optout_token_invalido_e_rejeitado(client):
    resposta = client.get("/api/v1/opt-out/email/token-forjado")
    assert resposta.status_code == 422


def test_optout_whatsapp_por_palavra_chave(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    """E9-H2: opt-out por palavra-chave no WhatsApp."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    resposta = client.post(
        "/api/v1/webhooks/whatsapp",
        json={"tenant_id": "tenant-teste", "telefone": decisor.telefone, "texto": "SAIR"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["suprimido"] is True


def test_lista_supressao_consultada_antes_do_envio(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp
):
    """E9-H2: lista de supressão consultada antes de qualquer novo envio."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_WHATSAPP_PRIMEIRO)

    client.post(
        "/api/v1/webhooks/whatsapp",
        json={"tenant_id": "tenant-teste", "telefone": decisor.telefone, "texto": "PARAR"},
    )

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["enviadas"] == 0
    assert fake_whatsapp.envios == []
