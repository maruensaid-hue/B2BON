"""Envio imediato ao aprovar/ativar (visto em produção em 09/11/2026: o cron do GitHub levou ~1 h entre rodadas e o WhatsApp de teste
aprovado não chegava). O que já está no horário sai na hora; o resto continua com o cron."""

import pytest

from app.api import envio_imediato
from app.core.config import settings
from tests.integration.test_envios import _TOQUES_WHATSAPP_PRIMEIRO, _aprovar_tudo, _fixar_relogio_comercial


@pytest.fixture()
def envio_imediato_ligado(monkeypatch, fake_whatsapp, fake_email):
    monkeypatch.setattr(settings, "envio_imediato_ao_aprovar", True)
    monkeypatch.setattr(envio_imediato.deps, "resolver_whatsapp_provider", lambda tenant_id, db: fake_whatsapp)
    monkeypatch.setattr(envio_imediato.deps, "resolver_email_provider", lambda tenant_id, db: fake_email)


def _gerar(client, conta_id: int) -> dict:
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência Teste", "toques": _TOQUES_WHATSAPP_PRIMEIRO}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    return cadencia


def test_ativar_a_cadencia_envia_na_hora_o_primeiro_toque(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, envio_imediato_ligado, monkeypatch
):
    _fixar_relogio_comercial(monkeypatch)
    conta, _ = criar_conta_com_decisor()
    cadencia = _gerar(client, conta.id)
    _aprovar_tudo(client, cadencia["id"])
    assert fake_whatsapp.envios == []  # ainda sem agendamento: a cadência não foi ativada

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 200
    assert len(fake_whatsapp.envios) == 1  # só o toque 1 está no horário; os outros ficam para o cron
    assert fake_whatsapp.envios[0]["tipo"] == "template"
    # O cron, rodando depois, não manda de novo.
    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 0


def test_aprovar_mensagem_que_ja_venceu_envia_na_hora(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, envio_imediato_ligado, monkeypatch, db_session
):
    from app.models.mensagem import Mensagem

    _fixar_relogio_comercial(monkeypatch)
    conta, _ = criar_conta_com_decisor()
    cadencia = _gerar(client, conta.id)
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    item_whatsapp = next(item for item in itens if item["canal"] == "whatsapp")
    mensagem = db_session.get(Mensagem, item_whatsapp["mensagem_id"])
    mensagem.agendado_para = envio_imediato.envio_service.datetime.now()
    db_session.commit()

    resposta = client.post(f"/api/v1/aprovacoes/{item_whatsapp['aprovacao_id']}/aprovar")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "aprovado"
    assert len(fake_whatsapp.envios) == 1


def test_falha_no_envio_imediato_nao_derruba_a_aprovacao(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, envio_imediato_ligado, monkeypatch
):
    def quebra(tenant_id, db):
        raise RuntimeError("credencial indecifrável")

    _fixar_relogio_comercial(monkeypatch)
    monkeypatch.setattr(envio_imediato.deps, "resolver_whatsapp_provider", quebra)
    conta, _ = criar_conta_com_decisor()
    cadencia = _gerar(client, conta.id)
    _aprovar_tudo(client, cadencia["id"])

    resposta = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert resposta.status_code == 200
    assert fake_whatsapp.envios == []


def test_chave_desligada_deixa_tudo_para_o_cron(client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, monkeypatch):
    _fixar_relogio_comercial(monkeypatch)
    conta, _ = criar_conta_com_decisor()
    cadencia = _gerar(client, conta.id)
    _aprovar_tudo(client, cadencia["id"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert fake_whatsapp.envios == []
    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 1
