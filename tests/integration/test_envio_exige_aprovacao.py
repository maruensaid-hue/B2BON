"""Mensagem comercial de cadência nunca sai sem aprovação humana.

Duas travas independentes, ambas exercitadas aqui:
1. `ativar` recusa cadência com toque pendente ou rejeitado (nada é agendado);
2. o dispatcher de envio só seleciona mensagens `aprovado`/`falhou` (defesa em profundidade: mesmo uma mensagem pendente com
   `agendado_para` já vencido, por bug ou adulteração, não sai)."""

from datetime import UTC, datetime, timedelta

from app.models.mensagem import Mensagem

TOQUES = [
    {"ordem": 1, "canal": "whatsapp", "intervalo_dias_apos_anterior": 0, "template_whatsapp_id": "prospeccao_inicial"},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
]


def _criar_e_gerar(client, conta_id: int) -> dict:
    resposta = client.post("/api/v1/cadencias", json={"nome": "Cadência sem aprovação", "toques": TOQUES})
    assert resposta.status_code in (200, 201), resposta.text
    cadencia = resposta.json()
    gerada = client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    assert gerada.status_code in (200, 201), gerada.text
    return cadencia


def _itens(client, cadencia_id: int) -> list[dict]:
    return client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia_id}).json()


def _aprovar_tudo(client, cadencia_id: int) -> None:
    for item in _itens(client, cadencia_id):
        assert client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar").status_code == 200


def test_cadencia_com_toques_pendentes_nao_pode_ser_ativada_e_nada_e_enviado(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, fake_email
):
    conta, _ = criar_conta_com_decisor()
    cadencia = _criar_e_gerar(client, conta.id)
    itens = _itens(client, cadencia["id"])
    assert itens and {i["mensagem_status"] for i in itens} == {"aguardando_aprovacao"}

    ativacao = client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")

    assert ativacao.status_code >= 400  # recusada: há toques pendentes de aprovação
    assert all(i["agendado_para"] is None for i in _itens(client, cadencia["id"]))
    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 0
    assert fake_whatsapp.envios == [] and fake_email.envios == []


def test_mensagem_pendente_com_horario_vencido_nunca_e_enviada_pelo_dispatcher(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, fake_email, db_session
):
    conta, _ = criar_conta_com_decisor()
    cadencia = _criar_e_gerar(client, conta.id)
    vencido = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    for mensagem in db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"]):
        assert mensagem.status == "aguardando_aprovacao"
        mensagem.agendado_para = vencido  # simula agendamento indevido, sem passar pela aprovação
    db_session.commit()

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["enviadas"] == 0
    assert fake_whatsapp.envios == [] and fake_email.envios == []
    assert {m.status for m in db_session.query(Mensagem).filter_by(cadencia_id=cadencia["id"])} == {"aguardando_aprovacao"}


def test_so_depois_de_aprovada_e_ativada_a_mensagem_e_enviada(client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp):
    conta, _ = criar_conta_com_decisor()
    cadencia = _criar_e_gerar(client, conta.id)
    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 0

    _aprovar_tudo(client, cadencia["id"])
    assert client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar").status_code == 200

    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 1  # só o toque 1 vence agora
    assert len(fake_whatsapp.envios) == 1


def test_toque_rejeitado_impede_a_ativacao_e_nada_e_enviado(client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp):
    conta, _ = criar_conta_com_decisor()
    cadencia = _criar_e_gerar(client, conta.id)
    rejeitado, *demais = _itens(client, cadencia["id"])
    for item in demais:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")
    resposta = client.post(f"/api/v1/aprovacoes/{rejeitado['aprovacao_id']}/rejeitar", json={"motivo": "fora do tom"})
    assert resposta.status_code == 200, resposta.text

    assert client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar").status_code >= 400
    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 0
    assert fake_whatsapp.envios == []


def test_mensagem_cancelada_depois_de_aprovada_nao_e_enviada(client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp):
    conta, _ = criar_conta_com_decisor()
    cadencia = _criar_e_gerar(client, conta.id)
    _aprovar_tudo(client, cadencia["id"])
    assert client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar").status_code == 200
    primeiro_toque = next(i for i in _itens(client, cadencia["id"]) if i["canal"] == "whatsapp")

    cancelada = client.post(f"/api/v1/aprovacoes/mensagens/{primeiro_toque['mensagem_id']}/cancelar")
    assert cancelada.status_code == 200, cancelada.text

    assert client.post("/api/v1/envios/processar").json()["enviadas"] == 0
    assert fake_whatsapp.envios == []
