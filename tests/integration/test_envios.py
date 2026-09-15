from datetime import UTC, datetime

from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import aprovacao_service, cadencia_service, envio_service


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


# Raio-X 2026-09-15: só 1 toque de WhatsApp por cadência é permitido —
# só o de ordem 1 (o único que estes testes realmente exercitam, já que
# só ele fica agendado para "agora" logo após ativar).
_TOQUES_WHATSAPP_PRIMEIRO = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "prospeccao_inicial"},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 2},
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


def test_envio_whatsapp_preenche_botao_com_numero_do_vendedor(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, db_session
):
    """Raio-X 2026-09-15: variável do botão de redirecionamento vem do
    WhatsApp pessoal do vendedor responsável pela conta (`Conta.
    vendedor_usuario_id` -> `Usuario.whatsapp_pessoal`)."""
    from app.models.usuario import Usuario

    conta, decisor = criar_conta_com_decisor()
    vendedor = db_session.query(Usuario).filter_by(tenant_id="tenant-teste").first()
    vendedor.whatsapp_pessoal = "+5511911112222"
    conta.vendedor_usuario_id = vendedor.id
    db_session.commit()

    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_WHATSAPP_PRIMEIRO)
    client.post("/api/v1/envios/processar")

    assert len(fake_whatsapp.envios) == 1
    assert fake_whatsapp.envios[0]["variavel_botao"] == "+5511911112222"


def test_envio_whatsapp_sem_vendedor_nao_preenche_botao(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp
):
    """Conta sem vendedor atribuído: o envio segue normalmente, só sem
    preencher a variável do botão."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_WHATSAPP_PRIMEIRO)

    client.post("/api/v1/envios/processar")

    assert len(fake_whatsapp.envios) == 1
    assert fake_whatsapp.envios[0]["variavel_botao"] is None


def test_template_status_aprovacao_visivel(client):
    """E3-H2: templates com status de aprovação visível."""
    resposta = client.get("/api/v1/whatsapp/templates")

    assert resposta.status_code == 200
    templates = resposta.json()
    assert templates[0]["nome"] == "prospeccao_inicial"
    assert templates[0]["status"] == "aprovado"


def test_mensagem_livre_bloqueada_fora_da_janela_24h(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, db_session
):
    """E3-H2: mensagens livres apenas dentro da janela de atendimento de
    24h. Raio-X 2026-09-15: uma cadência não pode mais ter um toque de
    WhatsApp sem template (ver `cadencia_service._validar_no_maximo_um_whatsapp_com_template`)
    — o cenário de mensagem livre é montado direto via
    `aprovacao_service.criar_proposta`, que continua aceitando
    `template_id=None` (esse caminho não é exclusivo de cadência)."""
    conta, decisor = criar_conta_com_decisor()
    mensagem = aprovacao_service.criar_proposta(
        db_session, "tenant-teste", None, decisor.id, "whatsapp", None, "Oi, tudo bem?",
        StubPlanLimitsProvider(), agendado_para=datetime.now(UTC),
    )
    mensagem.status = "aprovado"
    db_session.commit()

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


def test_resposta_interrompe_cadencia_em_todos_os_canais_quando_habilitado(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia
):
    """E3-H3, raio-X 2026-09-15: resposta só interrompe a cadência em todos
    os canais quando `cancelar_ao_responder=True` é marcado explicitamente
    — deixou de ser o comportamento automático (ver teste abaixo)."""
    conta, decisor = criar_conta_com_decisor()
    cadencia = criar_cadencia(cancelar_ao_responder=True)
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


def test_resposta_nao_interrompe_cadencia_por_padrao(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, db_session
):
    """Raio-X 2026-09-15: o padrão agora é "continuar nutrindo" — uma
    resposta não cancela mais nada automaticamente, a menos que a
    cadência tenha marcado `cancelar_ao_responder=True`."""
    from app.models.mensagem import Mensagem

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
    assert resposta.json()["mensagens_canceladas"] == 0
    mensagens = db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"]).all()
    assert all(m.status == "aprovado" for m in mensagens)


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
        {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 1},
        {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
    ]
    _criar_gerar_aprovar_ativar(client, conta.id, toques)

    client.post("/api/v1/envios/processar")

    assert len(fake_email.envios) == 1
    envio = fake_email.envios[0]
    assert envio["remetente_nome"] == "Ana Vendas"
    assert envio["remetente_email"] == "ana@empresateste.com.br"
    assert "Atenciosamente, Ana" in envio["corpo"]
