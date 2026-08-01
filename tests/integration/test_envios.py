from datetime import UTC, datetime

from app.services import cadencia_service, envio_service


class _RelogioFixo:
    """Segunda-feira, horário comercial — usado só quando o teste precisa
    que o gate de dias úteis/horário do e-mail (E3-H3) deixe passar,
    independente do dia real em que os testes rodam."""

    _agora = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._agora


def _fixar_relogio_comercial(monkeypatch) -> None:
    monkeypatch.setattr(cadencia_service, "datetime", _RelogioFixo)
    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)


def _aprovar_tudo(client, cadencia_id: int) -> None:
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia_id}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")


def _criar_gerar_aprovar_ativar(client, conta_id: int, toques: list[dict]) -> dict:
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência Teste", "toques": toques}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    return cadencia


_TOQUES_WHATSAPP_PRIMEIRO = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "prospeccao_inicial"},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 2, "template_whatsapp_id": "prospeccao_inicial"},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
]


def test_envio_whatsapp_usa_apenas_o_provider_oficial(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp
):
    """E3-H2: envio exclusivamente via API oficial."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_WHATSAPP_PRIMEIRO)

    resposta = client.post("/api/v1/envios/processar")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["enviadas"] == 1  # só o toque 1 (ordem 1) está agendado para agora
    assert len(fake_whatsapp.envios) == 1
    assert fake_whatsapp.envios[0]["tipo"] == "template"


def test_template_status_aprovacao_visivel(client):
    """E3-H2: templates com status de aprovação visível."""
    resposta = client.get("/api/v1/whatsapp/templates")

    assert resposta.status_code == 200
    templates = resposta.json()
    assert templates[0]["nome"] == "prospeccao_inicial"
    assert templates[0]["status"] == "aprovado"


def test_mensagem_livre_bloqueada_fora_da_janela_24h(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp
):
    """E3-H2: mensagens livres apenas dentro da janela de atendimento de 24h."""
    conta, decisor = criar_conta_com_decisor()
    toques = [
        {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0},  # sem template = mensagem livre
        {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 1},
        {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 1},
        {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
        {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
    ]
    _criar_gerar_aprovar_ativar(client, conta.id, toques)

    resposta = client.post("/api/v1/envios/processar")

    assert resposta.json()["adiadas"] == 1
    assert fake_whatsapp.envios == []


def test_falha_de_envio_registra_motivo_e_permite_reprocessar(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp
):
    """E3-H2: falhas registradas com motivo e reprocessamento controlado."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_WHATSAPP_PRIMEIRO)
    fake_whatsapp.falhar_proximos = 1

    primeira = client.post("/api/v1/envios/processar").json()
    assert primeira["falhas"] == 1
    assert primeira["enviadas"] == 0

    eventos = client.get("/api/v1/auditoria").json()
    evento_falha = next(e for e in eventos if e["evento_tipo"] == "envio_falhou")
    assert evento_falha["detalhes"]["motivo"] == "falha simulada"

    segunda = client.post("/api/v1/envios/processar").json()
    assert segunda["enviadas"] == 1


def test_resposta_interrompe_cadencia_em_todos_os_canais(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia
):
    """E3-H3: resposta detectada interrompe a cadência daquele contato em todos os canais."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")

    resposta = client.post(
        "/api/v1/webhooks/whatsapp",
        json={"tenant_id": "tenant-teste", "telefone": decisor.telefone, "texto": "Tenho interesse, me liga"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["mensagens_canceladas"] == len(itens)


def test_remetente_e_assinatura_configuraveis_aplicados_no_envio(
    client, onboarding_completo, criar_conta_com_decisor, fake_email, monkeypatch
):
    """E3-H3: assinatura e identificação do remetente configuráveis por assinante."""
    _fixar_relogio_comercial(monkeypatch)
    client.put(
        "/api/v1/configuracao-envio",
        json={
            "remetente_nome": "Ana Vendas",
            "remetente_email": "ana@empresateste.com.br",
            "assinatura": "Atenciosamente, Ana",
            "horario_inicio": "09:00:00",
            "horario_fim": "18:00:00",
        },
    )
    conta, decisor = criar_conta_com_decisor()
    toques = [
        {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
        {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
        {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 1},
        {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
        {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
    ]
    _criar_gerar_aprovar_ativar(client, conta.id, toques)

    client.post("/api/v1/envios/processar")

    assert len(fake_email.envios) == 1
    envio = fake_email.envios[0]
    assert envio["remetente_nome"] == "Ana Vendas"
    assert envio["remetente_email"] == "ana@empresateste.com.br"
    assert "Atenciosamente, Ana" in envio["corpo"]
