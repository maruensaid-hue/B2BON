from app.models.decisor import Decisor
from app.models.registro_supressao_permanente import RegistroSupressaoPermanente

TENANT_ID = "tenant-teste"


def test_busca_titular_por_identificador(client, criar_conta_com_decisor):
    """E9-H3: busca de titular por identificadores."""
    conta, decisor = criar_conta_com_decisor()

    resposta = client.get("/api/v1/titulares/buscar", params={"identificador": decisor.email})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["encontrado"] is True
    assert corpo["decisor_id"] == decisor.id


def test_busca_titular_nao_encontrado(client):
    resposta = client.get("/api/v1/titulares/buscar", params={"identificador": "ninguem@nada.com"})
    assert resposta.status_code == 200
    assert resposta.json()["encontrado"] is False


def test_exportacao_dados_do_titular(client, criar_conta_com_decisor):
    """E9-H3: exportação dos dados tratados."""
    conta, decisor = criar_conta_com_decisor()

    resposta = client.get("/api/v1/titulares/exportar", params={"identificador": decisor.email})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["decisor"]["nome"] == decisor.nome
    assert corpo["conta"]["nome"] == conta.nome


def test_eliminacao_preserva_so_hash_de_supressao(client, db_session, criar_conta_com_decisor):
    """E9-H3: eliminação com preservação apenas do registro mínimo de supressão."""
    conta, decisor = criar_conta_com_decisor()
    decisor_id = decisor.id
    email = decisor.email

    resposta = client.delete("/api/v1/titulares", params={"identificador": email})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["eliminado"] is True
    assert corpo["identificador_hash"]

    assert db_session.query(Decisor).filter_by(id=decisor_id).one_or_none() is None
    supressao = db_session.query(RegistroSupressaoPermanente).filter_by(tenant_id=TENANT_ID).one()
    assert supressao.identificador_hash == corpo["identificador_hash"]
    assert email not in supressao.identificador_hash
