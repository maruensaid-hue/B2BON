from app.services import intent_service, rede_social_service
from app.services.errors import NaoAutorizado, NaoEncontrado

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def _criar_intent(db_session, tenant_id, visibilidade="publica", **overrides):
    dados = {
        "categoria": "backup",
        "titulo": "Backup imutável",
        "descricao": "Procuramos solução de backup imutável para 500 endpoints.",
        "requisitos": ["imutabilidade", "500 endpoints"],
        "faixa_orcamento": "R$ 50k-100k",
        "localizacao": "SP",
        "prazo": None,
        "perfil_fornecedor_desejado": "Fornecedor com certificação ISO 27001",
        "visibilidade": visibilidade,
    }
    dados.update(overrides)
    return intent_service.criar(db_session, tenant_id, None, **dados)


def test_criar_intent(db_session):
    intent = _criar_intent(db_session, TENANT_A)

    assert intent["titulo"] == "Backup imutável"
    assert intent["tenant_id"] == TENANT_A
    assert intent["status"] == "aberta"
    assert intent["visibilidade"] == "publica"


def test_listar_intent_publica_visivel_para_todos(db_session):
    _criar_intent(db_session, TENANT_A, visibilidade="publica")

    visivel_para_b = intent_service.listar(db_session, TENANT_B)

    assert len(visivel_para_b) == 1


def test_listar_intent_conexoes_invisivel_sem_conexao_aceita(db_session):
    _criar_intent(db_session, TENANT_A, visibilidade="conexoes")

    assert intent_service.listar(db_session, TENANT_B) == []
    # o próprio autor sempre vê a própria intent, mesmo restrita
    assert len(intent_service.listar(db_session, TENANT_A)) == 1


def test_listar_intent_conexoes_visivel_com_conexao_aceita(db_session):
    _criar_intent(db_session, TENANT_A, visibilidade="conexoes")
    conexao = rede_social_service.solicitar_conexao(db_session, TENANT_A, None, TENANT_B)
    rede_social_service.responder_conexao(db_session, TENANT_B, None, conexao.id, aceitar=True)

    assert len(intent_service.listar(db_session, TENANT_B)) == 1
    # tenant sem conexão continua sem ver
    assert intent_service.listar(db_session, TENANT_C) == []


def test_obter_visivel_levanta_nao_encontrado_quando_restrita(db_session):
    intent = _criar_intent(db_session, TENANT_A, visibilidade="conexoes")

    try:
        intent_service.obter_visivel(db_session, TENANT_B, intent["id"])
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_encerrar_apenas_pelo_autor(db_session):
    intent = _criar_intent(db_session, TENANT_A)

    try:
        intent_service.encerrar(db_session, TENANT_B, None, intent["id"])
        assert False, "deveria ter levantado NaoAutorizado"
    except NaoAutorizado:
        pass

    encerrada = intent_service.encerrar(db_session, TENANT_A, None, intent["id"])
    assert encerrada["status"] == "cancelada"


def test_marcar_atendida(db_session):
    intent = _criar_intent(db_session, TENANT_A)

    atendida = intent_service.marcar_atendida(db_session, TENANT_A, None, intent["id"])

    assert atendida["status"] == "atendida"


def test_encerrar_intent_inexistente_levanta_erro(db_session):
    try:
        intent_service.encerrar(db_session, TENANT_A, None, 9999)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
