import pytest

from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.services import aprovacao_service

TENANT_ID = "tenant-teste"


@pytest.fixture()
def cadencia_e_decisor(db_session):
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()
    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    cadencia = Cadencia(tenant_id=TENANT_ID, conta_id=conta.id, nome="Cadência", status="rascunho")
    db_session.add(cadencia)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor")
    db_session.add(decisor)
    db_session.commit()
    return cadencia, decisor, conta


def _propor_mensagem(db_session, cadencia, decisor, canal="email", template_id="tpl-1", conteudo="Olá {{nome}}"):
    return aprovacao_service.criar_proposta(db_session, TENANT_ID, cadencia.id, decisor.id, canal, template_id, conteudo)


def test_fila_filtra_por_canal_conta_e_cadencia(client, db_session, cadencia_e_decisor):
    """E4-H1: fila com filtros por canal, conta e cadência."""
    cadencia, decisor, conta = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor, canal="email")
    _propor_mensagem(db_session, cadencia, decisor, canal="whatsapp")

    resposta = client.get("/api/v1/aprovacoes", params={"canal": "email"})

    assert resposta.status_code == 200
    itens = resposta.json()
    assert len(itens) == 1
    assert itens[0]["canal"] == "email"
    assert itens[0]["conta_id"] == conta.id
    assert itens[0]["cadencia_id"] == cadencia.id


def test_aprovar_item_da_fila(client, db_session, cadencia_e_decisor):
    cadencia, decisor, _ = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor)
    aprovacao_id = client.get("/api/v1/aprovacoes").json()[0]["aprovacao_id"]

    resposta = client.post(f"/api/v1/aprovacoes/{aprovacao_id}/aprovar")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "aprovado"
    assert resposta.json()["aprovador_id"] == "user-teste"


def test_rejeitar_item_da_fila(client, db_session, cadencia_e_decisor):
    cadencia, decisor, _ = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor)
    aprovacao_id = client.get("/api/v1/aprovacoes").json()[0]["aprovacao_id"]

    resposta = client.post(f"/api/v1/aprovacoes/{aprovacao_id}/rejeitar", json={"motivo": "fora do tom"})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "rejeitado"


def test_lote_so_permite_mesmo_template(client, db_session, cadencia_e_decisor):
    """E4-H1: aprovação em lote disponível apenas para itens do mesmo template."""
    cadencia, decisor, _ = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor, template_id="tpl-A")
    _propor_mensagem(db_session, cadencia, decisor, template_id="tpl-B")
    ids = [item["aprovacao_id"] for item in client.get("/api/v1/aprovacoes").json()]

    resposta = client.post("/api/v1/aprovacoes/aprovar-lote", json={"ids": ids})

    assert resposta.status_code == 422


def test_lote_aprova_mesmo_template(client, db_session, cadencia_e_decisor):
    cadencia, decisor, _ = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor, template_id="tpl-A")
    _propor_mensagem(db_session, cadencia, decisor, template_id="tpl-A")
    ids = [item["aprovacao_id"] for item in client.get("/api/v1/aprovacoes").json()]

    resposta = client.post("/api/v1/aprovacoes/aprovar-lote", json={"ids": ids})

    assert resposta.status_code == 200
    assert all(item["status"] == "aprovado" for item in resposta.json())


def test_editar_mensagem_preserva_variaveis_validas(client, db_session, cadencia_e_decisor):
    """E4-H2: edição inline preservando variáveis de personalização válidas."""
    cadencia, decisor, _ = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor, conteudo="Olá {{nome}}")
    aprovacao_id = client.get("/api/v1/aprovacoes").json()[0]["aprovacao_id"]

    resposta = client.put(
        f"/api/v1/aprovacoes/{aprovacao_id}/mensagem", json={"conteudo": "Olá {{nome}}, tudo bem na {{empresa}}?"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["conteudo"] == "Olá {{nome}}, tudo bem na {{empresa}}?"

    # E4-H2: versão editada registrada como edição humana
    item = client.get("/api/v1/aprovacoes").json()[0]
    assert item["status"] == "editado"


def test_editar_mensagem_rejeita_variavel_invalida(client, db_session, cadencia_e_decisor):
    cadencia, decisor, _ = cadencia_e_decisor
    _propor_mensagem(db_session, cadencia, decisor, conteudo="Olá {{nome}}")
    aprovacao_id = client.get("/api/v1/aprovacoes").json()[0]["aprovacao_id"]

    resposta = client.put(
        f"/api/v1/aprovacoes/{aprovacao_id}/mensagem", json={"conteudo": "Use {{codigo_secreto}}"}
    )

    assert resposta.status_code == 422
