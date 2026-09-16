from datetime import UTC, datetime

from app.services import cadencia_service, envio_service, reputacao_service

TENANT_ID = "tenant-teste"


class _RelogioFixo:
    _agora = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._agora


def _aprovar_tudo(client, cadencia_id: int) -> None:
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia_id}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")


# Raio-X 2026-09-15: só 1 toque de WhatsApp por cadência.
_TOQUES_WHATSAPP_PRIMEIRO = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "prospeccao_inicial"},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
]


def test_canal_pausado_e_pulado_pelo_dispatcher_de_envio(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, db_session, monkeypatch
):
    """E10-H2: pausa automática bloqueia novos envios sem quebrar a cadência (adiada, não falha)."""
    monkeypatch.setattr(cadencia_service, "datetime", _RelogioFixo)
    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)

    conta, decisor = criar_conta_com_decisor()
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência", "toques": _TOQUES_WHATSAPP_PRIMEIRO}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    resposta_reputacao = client.post(
        "/api/v1/webhooks/reputacao",
        json={"tenant_id": TENANT_ID, "canal": "whatsapp", "tipo_evento": "enviado", "quantidade": 100},
    )
    assert resposta_reputacao.status_code == 200
    client.post(
        "/api/v1/webhooks/reputacao",
        json={"tenant_id": TENANT_ID, "canal": "whatsapp", "tipo_evento": "bounce", "quantidade": 10},
    )
    assert client.get("/api/v1/canais/whatsapp/saude").json()["pausado"] is True

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["enviadas"] == 0
    assert resultado["adiadas"] == 1
    assert fake_whatsapp.envios == []


def test_reativar_canal_permite_envio_apos_pausa(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, monkeypatch
):
    monkeypatch.setattr(cadencia_service, "datetime", _RelogioFixo)
    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)

    conta, decisor = criar_conta_com_decisor()
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência", "toques": _TOQUES_WHATSAPP_PRIMEIRO}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    client.post(
        "/api/v1/webhooks/reputacao",
        json={"tenant_id": TENANT_ID, "canal": "whatsapp", "tipo_evento": "enviado", "quantidade": 100},
    )
    client.post(
        "/api/v1/webhooks/reputacao",
        json={"tenant_id": TENANT_ID, "canal": "whatsapp", "tipo_evento": "bounce", "quantidade": 10},
    )

    resposta_reativar = client.post("/api/v1/canais/whatsapp/reativar")
    assert resposta_reativar.json()["pausado"] is False

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["enviadas"] == 1


_TOQUES_SEM_EMAIL = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "prospeccao_inicial"},
    {"ordem": 2, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
]


def test_ativar_cadencia_com_toque_de_email_bloqueada_por_canal_pausado(
    client, onboarding_completo, criar_conta_com_decisor, db_session, monkeypatch
):
    """Raio-X 2026-09-16 (Relatório de Entrega): não deixa ativar uma nova
    cadência com toque de e-mail enquanto o canal está pausado por
    bounce — antes disso passava direto e só adiava na hora do envio."""
    monkeypatch.setattr(cadencia_service, "datetime", _RelogioFixo)
    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)

    conta, decisor = criar_conta_com_decisor()
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência", "toques": _TOQUES_WHATSAPP_PRIMEIRO}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])

    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 10)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 1)

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 409


def test_ativar_cadencia_sem_toque_de_email_nao_e_bloqueada_por_email_pausado(
    client, onboarding_completo, criar_conta_com_decisor, db_session, monkeypatch
):
    """Só o canal de fato usado pela cadência é checado — uma cadência
    sem toque de e-mail não deveria ser afetada pela pausa do e-mail."""
    monkeypatch.setattr(cadencia_service, "datetime", _RelogioFixo)
    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)

    conta, decisor = criar_conta_com_decisor()
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência", "toques": _TOQUES_SEM_EMAIL}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    _aprovar_tudo(client, cadencia["id"])

    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 10)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 1)

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 200
