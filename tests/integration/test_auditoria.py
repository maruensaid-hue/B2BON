import pytest

from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.services import aprovacao_service

TENANT_ID = "tenant-teste"
ATOR_ID = "1"  # Onda A: id do usuário de teste padrão da fixture `client`


@pytest.fixture()
def aprovacao_registrada(client, db_session):
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

    aprovacao_service.criar_proposta(db_session, TENANT_ID, cadencia.id, decisor.id, "email", "tpl-1", "Olá {{nome}}")
    aprovacao_id = client.get("/api/v1/aprovacoes").json()[0]["aprovacao_id"]
    client.post(f"/api/v1/aprovacoes/{aprovacao_id}/aprovar")

    return conta


def test_auditoria_imutavel_identifica_aprovador(client, aprovacao_registrada):
    """E4-H3: registro imutável por evento com identificação do aprovador."""
    resposta = client.get("/api/v1/auditoria")

    assert resposta.status_code == 200
    eventos = resposta.json()
    evento_aprovacao = next(e for e in eventos if e["evento_tipo"] == "aprovacao_aprovada")
    assert evento_aprovacao["ator_id"] == ATOR_ID
    assert evento_aprovacao["tenant_id"] == "tenant-teste"


def test_consulta_por_conta_e_canal(client, aprovacao_registrada):
    """E4-H3: consulta por período, assinante, conta e canal."""
    conta = aprovacao_registrada

    resposta = client.get("/api/v1/auditoria", params={"conta_id": conta.id, "canal": "email"})

    assert resposta.status_code == 200
    eventos = resposta.json()
    assert len(eventos) >= 1
    assert all(e["conta_id"] == conta.id for e in eventos)
    assert all(e["canal"] == "email" for e in eventos)

    sem_resultado = client.get("/api/v1/auditoria", params={"conta_id": conta.id, "canal": "whatsapp"})
    assert sem_resultado.json() == []


def test_exportacao_csv(client, aprovacao_registrada):
    """E4-H3: exportação da trilha em CSV."""
    resposta = client.get("/api/v1/auditoria/exportar.csv")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    linhas = resposta.text.splitlines()
    assert linhas[0].startswith("id,tenant_id,evento_tipo")
    assert len(linhas) > 1
