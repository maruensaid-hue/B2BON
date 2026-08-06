from datetime import UTC, datetime, timedelta

from app.models.decisor import Decisor
from app.models.registro_supressao_permanente import RegistroSupressaoPermanente
from app.services import titular_service

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


def test_expirar_inativos_elimina_decisor_antigo_sem_interacao(db_session, criar_conta_com_decisor):
    """Raio-X de produção: sem retenção automática, dado pessoal de quem
    nunca virou cliente se acumula indefinidamente."""
    _, decisor = criar_conta_com_decisor()
    decisor.criado_em = datetime.now(UTC) - timedelta(days=800)
    decisor.ultima_interacao_em = None
    db_session.commit()

    resultado = titular_service.expirar_inativos(db_session, TENANT_ID, dias=730)

    assert resultado["decisores_expirados"] == 1
    assert db_session.query(Decisor).filter_by(id=decisor.id).one_or_none() is None


def test_expirar_inativos_preserva_decisor_com_interacao_recente(db_session, criar_conta_com_decisor):
    _, decisor = criar_conta_com_decisor()
    decisor.criado_em = datetime.now(UTC) - timedelta(days=800)
    decisor.ultima_interacao_em = datetime.now(UTC) - timedelta(days=10)
    db_session.commit()

    resultado = titular_service.expirar_inativos(db_session, TENANT_ID, dias=730)

    assert resultado["decisores_expirados"] == 0
    assert db_session.query(Decisor).filter_by(id=decisor.id).one_or_none() is not None


def test_expirar_inativos_nunca_apaga_decisor_de_conta_que_virou_cliente(db_session, criar_conta_com_decisor):
    """Guardrail de negócio: virar cliente muda a base legal de retenção
    (execução de contrato), não é mais só legítimo interesse de prospecção."""
    conta, decisor = criar_conta_com_decisor()
    decisor.criado_em = datetime.now(UTC) - timedelta(days=800)
    decisor.ultima_interacao_em = None
    conta.cliente_desde = datetime.now(UTC) - timedelta(days=500)
    db_session.commit()

    resultado = titular_service.expirar_inativos(db_session, TENANT_ID, dias=730)

    assert resultado["decisores_expirados"] == 0
    assert db_session.query(Decisor).filter_by(id=decisor.id).one_or_none() is not None


def test_expirar_inativos_preserva_decisor_recente(db_session, criar_conta_com_decisor):
    """Recém-criado ainda não teve tempo de interagir — não pode ser
    penalizado por isso."""
    _, decisor = criar_conta_com_decisor()

    resultado = titular_service.expirar_inativos(db_session, TENANT_ID, dias=730)

    assert resultado["decisores_expirados"] == 0
    assert db_session.query(Decisor).filter_by(id=decisor.id).one_or_none() is not None
