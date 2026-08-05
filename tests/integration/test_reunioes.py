import pytest

from app.models.reuniao import Reuniao
from app.services import reuniao_service

TENANT_ID = "tenant-teste"


def _propor_e_confirmar(client, decisor_id: int) -> dict:
    reuniao = client.post(
        f"/api/v1/decisores/{decisor_id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = reuniao["horarios_propostos"][0]
    return client.post(f"/api/v1/reunioes/{reuniao['id']}/confirmar", json={"horario_escolhido": horario}).json()


def test_propoe_tres_horarios(client, criar_conta_com_decisor):
    """E6-H1: integração com a agenda do vendedor e proposta de 3 horários."""
    conta, decisor = criar_conta_com_decisor()

    resposta = client.post(f"/api/v1/decisores/{decisor.id}/reunioes/propor", json={"vendedor_id": "vendedor-1"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert len(corpo["horarios_propostos"]) == 3
    assert corpo["status"] == "horarios_propostos"


def test_confirmar_cria_oportunidade_no_crm_automaticamente(client, criar_conta_com_decisor, fake_crm):
    """E6-H2: oportunidade criada no CRM no ato do agendamento, sem ação humana."""
    conta, decisor = criar_conta_com_decisor()

    confirmada = _propor_e_confirmar(client, decisor.id)

    assert confirmada["status"] == "agendada"
    assert confirmada["origem_crm_id"] is not None
    assert confirmada["origem_crm_id"] in fake_crm.oportunidades
    assert confirmada["link_reuniao"]


def test_confirmar_falha_sem_registro_no_crm_nao_agenda(client, db_session, criar_conta_com_decisor, fake_crm):
    """E6-H2: teste automatizado garante nenhuma reunião do motor sem registro no CRM."""
    conta, decisor = criar_conta_com_decisor()
    reuniao = client.post(
        f"/api/v1/decisores/{decisor.id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = reuniao["horarios_propostos"][0]
    fake_crm.falhar_proximos = 1

    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/reunioes/{reuniao['id']}/confirmar", json={"horario_escolhido": horario})

    ainda_pendente = db_session.query(Reuniao).filter_by(id=reuniao["id"]).one()
    assert ainda_pendente.status == "horarios_propostos"
    assert ainda_pendente.origem_crm_id is None


def test_status_realizado_no_show_refletido(client, criar_conta_com_decisor):
    """E6-H2: status realizado/no-show capturado e refletido na métrica."""
    conta, decisor = criar_conta_com_decisor()
    confirmada = _propor_e_confirmar(client, decisor.id)

    resposta = client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "no_show"})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "no_show"


def test_reagendamento_pelo_proprio_lead_via_token(client, criar_conta_com_decisor):
    """E6-H1: reagendamento pelo próprio lead, via link/token — endpoint público."""
    conta, decisor = criar_conta_com_decisor()
    proposta = client.post(
        f"/api/v1/decisores/{decisor.id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    confirmada = client.post(
        f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": proposta["horarios_propostos"][0]}
    ).json()

    token = reuniao_service.gerar_token_reagendamento(TENANT_ID, confirmada["id"])
    novo_horario = proposta["horarios_propostos"][1]

    resposta = client.post(f"/api/v1/reunioes/reagendar/{token}", json={"novo_horario": novo_horario})

    assert resposta.status_code == 200
    nova = resposta.json()
    assert nova["status"] == "agendada"
    assert nova["reagendado_de_id"] == confirmada["id"]
    assert nova["origem_crm_id"] is not None


def test_reagendamento_token_invalido_e_rejeitado(client):
    resposta = client.post("/api/v1/reunioes/reagendar/token-forjado", json={"novo_horario": "2030-01-01T10:00:00"})
    assert resposta.status_code == 422


def test_confirmar_qualificacao_grava_feedback_ligado_ao_score(client, criar_conta_com_decisor):
    """E6-H3: prompt pós-reunião de 1 toque; feedback alimenta o scoring."""
    conta, decisor = criar_conta_com_decisor()
    confirmada = _propor_e_confirmar(client, decisor.id)

    resposta = client.post(
        f"/api/v1/reunioes/{confirmada['id']}/confirmar-qualificacao",
        json={"qualificada": True, "motivo": None},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["qualificada_confirmada"] is True


def test_listar_reunioes_via_api(client, criar_conta_com_decisor):
    """Onda J: não existia rota de listagem, só ações por id — faltava
    tela de Reuniões no frontend."""
    conta, decisor = criar_conta_com_decisor()
    confirmada = _propor_e_confirmar(client, decisor.id)

    resposta = client.get("/api/v1/reunioes")

    assert resposta.status_code == 200
    assert any(r["id"] == confirmada["id"] for r in resposta.json())


def test_listar_reunioes_filtra_por_status(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    confirmada = _propor_e_confirmar(client, decisor.id)
    client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "realizada"})

    agendadas = client.get("/api/v1/reunioes", params={"status": "agendada"}).json()
    realizadas = client.get("/api/v1/reunioes", params={"status": "realizada"}).json()

    assert not any(r["id"] == confirmada["id"] for r in agendadas)
    assert any(r["id"] == confirmada["id"] for r in realizadas)


def test_dossie_apos_reuniao_realizada(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    confirmada = _propor_e_confirmar(client, decisor.id)
    client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "realizada"})

    resposta = client.get(f"/api/v1/reunioes/{confirmada['id']}/dossie")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["decisor_nome"] == decisor.nome
    assert corpo["conta_nome"] == conta.nome
