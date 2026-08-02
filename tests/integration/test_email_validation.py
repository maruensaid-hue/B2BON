from datetime import UTC, datetime

from app.services import cadencia_service, envio_service

TENANT_ID = "tenant-teste"


class _RelogioFixo:
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


_TOQUES_EMAIL_PRIMEIRO = [
    {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
    {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 1},
    {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
]


def _criar_gerar_aprovar_ativar(client, conta_id: int) -> dict:
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência", "toques": _TOQUES_EMAIL_PRIMEIRO}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    return cadencia


def test_email_invalido_e_descartado_antes_do_envio_com_motivo(
    client, onboarding_completo, criar_conta_com_decisor, fake_email, fake_email_validacao, monkeypatch
):
    """E10-H3: verificação prévia com descarte de endereços inválidos e registro do motivo."""
    _fixar_relogio_comercial(monkeypatch)
    fake_email_validacao.dominios_invalidos.add("invalido.test")
    conta, decisor = criar_conta_com_decisor(email="contato@invalido.test")
    _criar_gerar_aprovar_ativar(client, conta.id)

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["descartadas_email_invalido"] == 1
    assert resultado["enviadas"] == 0
    assert resultado["falhas"] == 0
    assert fake_email.envios == []

    evento = next(e for e in client.get("/api/v1/auditoria").json() if e["evento_tipo"] == "email_invalido_descartado")
    assert "domínio" in evento["detalhes"]["motivo"]


def test_email_valido_segue_fluxo_normal_de_envio(
    client, onboarding_completo, criar_conta_com_decisor, fake_email, fake_email_validacao, monkeypatch
):
    _fixar_relogio_comercial(monkeypatch)
    conta, decisor = criar_conta_com_decisor()  # e-mail padrão válido
    _criar_gerar_aprovar_ativar(client, conta.id)

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["descartadas_email_invalido"] == 0
    assert resultado["enviadas"] == 1
    assert len(fake_email.envios) == 1
