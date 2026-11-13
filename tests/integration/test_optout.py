from app.services import optout_service

# Raio-X 2026-09-15: só 1 toque de WhatsApp por cadência.
_TOQUES_WHATSAPP_PRIMEIRO = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "x"},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 2},
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


def test_optout_email_efeito_imediato_todos_canais(client, db_session, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    """E9-H2: opt-out via link do e-mail, efeito imediato em todos os canais."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()

    token = optout_service.gerar_token("tenant-teste", decisor.id)
    resposta = client.post(f"/api/v1/opt-out/email/{token}", data={"List-Unsubscribe": "One-Click"})

    assert resposta.status_code == 200
    assert "descadastro feito" in resposta.text
    db_session.refresh(decisor)
    assert decisor.suprimido_em is not None
    restantes = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    assert len(itens) > 0 and all(i["mensagem_status"] == "cancelado" for i in restantes)


def test_abrir_o_link_nao_descadastra(client, db_session, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    """Filtro de segurança corporativo abre (GET) todo link do e-mail: o GET só mostra a confirmação, nada muda (13/11/2026)."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    token = optout_service.gerar_token("tenant-teste", decisor.id)
    resposta = client.get(f"/api/v1/opt-out/email/{token}")

    assert resposta.status_code == 200
    assert 'method="post"' in resposta.text and "Confirmar descadastro" in resposta.text
    db_session.refresh(decisor)
    assert decisor.suprimido_em is None
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    assert itens and all(i["mensagem_status"] != "cancelado" for i in itens)


def test_optout_token_invalido_e_rejeitado(client):
    assert client.get("/api/v1/opt-out/email/token-forjado").status_code == 422
    assert client.post("/api/v1/opt-out/email/token-forjado").status_code == 422


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
