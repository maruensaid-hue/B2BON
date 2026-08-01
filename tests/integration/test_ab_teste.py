from app.models.mensagem import Mensagem
from app.models.toque_cadencia import ToqueCadencia
from app.services import cadencia_service

_TOQUES_COM_AB_NO_PRIMEIRO = [
    {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0, "ab_teste_habilitado": True},
    {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 2, "template_whatsapp_id": "x"},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 3},
    {"ordem": 4, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
    {"ordem": 5, "canal": "whatsapp", "intervalo_dias_apos_anterior": 3, "template_whatsapp_id": "x"},
]


def test_toque_com_ab_habilitado_distribui_variantes_por_decisor(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, db_session
):
    """E3-H5: duas variantes por toque com distribuição controlada."""
    _, decisor1 = criar_conta_com_decisor(email="d1@teste.com", telefone="+5511900000001")
    _, decisor2 = criar_conta_com_decisor(email="d2@teste.com", telefone="+5511900000002")
    cadencia = criar_cadencia(toques=_TOQUES_COM_AB_NO_PRIMEIRO)

    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [decisor1.conta_id, decisor2.conta_id]})

    toque_ab = db_session.query(ToqueCadencia).filter_by(cadencia_id=cadencia["id"], ordem=1).one()
    toque_sem_ab = db_session.query(ToqueCadencia).filter_by(cadencia_id=cadencia["id"], ordem=3).one()

    variante_d1 = db_session.query(Mensagem).filter_by(toque_cadencia_id=toque_ab.id, decisor_id=decisor1.id).one()
    variante_d2 = db_session.query(Mensagem).filter_by(toque_cadencia_id=toque_ab.id, decisor_id=decisor2.id).one()
    mensagem_sem_ab = db_session.query(Mensagem).filter_by(toque_cadencia_id=toque_sem_ab.id, decisor_id=decisor1.id).one()

    assert variante_d1.variante_ab == cadencia_service.variante_ab_para_decisor(decisor1.id)
    assert variante_d2.variante_ab == cadencia_service.variante_ab_para_decisor(decisor2.id)
    assert variante_d1.variante_ab in ("A", "B")
    assert mensagem_sem_ab.variante_ab is None


def test_endpoint_relatorio_teste_ab_expoe_taxas_por_variante(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, db_session
):
    _, decisor1 = criar_conta_com_decisor(email="d1@teste.com", telefone="+5511900000001")
    _, decisor2 = criar_conta_com_decisor(email="d2@teste.com", telefone="+5511900000002")
    cadencia = criar_cadencia(toques=_TOQUES_COM_AB_NO_PRIMEIRO)
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [decisor1.conta_id, decisor2.conta_id]})

    resposta = client.get(f"/api/v1/cadencias/{cadencia['id']}/teste-ab")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "variante_a" in corpo and "variante_b" in corpo
    assert "vencedora" in corpo
