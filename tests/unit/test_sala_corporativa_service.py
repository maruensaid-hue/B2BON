from app.services import rede_social_service, sala_corporativa_service
from app.services.errors import NaoAutorizado, NaoEncontrado, RegraNegocioViolada

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def _conectar(db_session, tenant_a, tenant_b):
    conexao = rede_social_service.solicitar_conexao(db_session, tenant_a, None, tenant_b)
    rede_social_service.responder_conexao(db_session, tenant_b, None, conexao.id, aceitar=True)


def test_abrir_sala_exige_conexao_aceita(db_session):
    try:
        sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_abrir_sala_com_a_propria_empresa_levanta_erro(db_session):
    try:
        sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_A)
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_abrir_sala_cria_canal_general_automatico(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)

    sala = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)

    canais = sala_corporativa_service.listar_canais(db_session, TENANT_A, sala["id"])
    assert len(canais) == 1
    assert canais[0]["tipo"] == "GENERAL"


def test_abrir_sala_e_idempotente_e_normalizada_por_par(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)

    sala_de_a = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)
    sala_de_b = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_B, None, TENANT_A)

    assert sala_de_a["id"] == sala_de_b["id"]
    assert sala_de_a["tenant_id_alvo"] == TENANT_B
    assert sala_de_b["tenant_id_alvo"] == TENANT_A


def test_listar_salas_do_tenant(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)

    salas_a = sala_corporativa_service.listar_salas(db_session, TENANT_A)
    salas_c = sala_corporativa_service.listar_salas(db_session, TENANT_C)

    assert len(salas_a) == 1
    assert salas_c == []


def test_tenant_de_fora_nao_acessa_sala(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    sala = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)

    try:
        sala_corporativa_service.listar_canais(db_session, TENANT_C, sala["id"])
        assert False, "deveria ter levantado NaoAutorizado"
    except NaoAutorizado:
        pass


def test_criar_canal_custom_exige_nome(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    sala = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)

    try:
        sala_corporativa_service.criar_canal(db_session, TENANT_A, None, sala["id"], "CUSTOM", None)
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass

    canal = sala_corporativa_service.criar_canal(db_session, TENANT_A, None, sala["id"], "CUSTOM", "Integração API")
    assert canal["nome"] == "Integração API"


def test_criar_canal_tipo_invalido_levanta_erro(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    sala = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)

    try:
        sala_corporativa_service.criar_canal(db_session, TENANT_A, None, sala["id"], "INVALIDO", None)
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_enviar_e_listar_mensagens_no_canal(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    sala = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)
    canal_general = sala_corporativa_service.listar_canais(db_session, TENANT_A, sala["id"])[0]

    sala_corporativa_service.enviar_mensagem_sala(db_session, TENANT_A, None, canal_general["id"], "Olá!", None)
    sala_corporativa_service.enviar_mensagem_sala(
        db_session, TENANT_B, None, canal_general["id"], "Oi, tudo bem?", "https://exemplo.com/doc.pdf"
    )

    mensagens = sala_corporativa_service.listar_mensagens(db_session, TENANT_A, canal_general["id"])
    assert [m["texto"] for m in mensagens] == ["Olá!", "Oi, tudo bem?"]
    assert mensagens[1]["documento_url"] == "https://exemplo.com/doc.pdf"
    assert mensagens[1]["empresa_nome"] == TENANT_B


def test_tenant_de_fora_nao_envia_mensagem(db_session):
    _conectar(db_session, TENANT_A, TENANT_B)
    sala = sala_corporativa_service.abrir_ou_obter_sala(db_session, TENANT_A, None, TENANT_B)
    canal_general = sala_corporativa_service.listar_canais(db_session, TENANT_A, sala["id"])[0]

    try:
        sala_corporativa_service.enviar_mensagem_sala(db_session, TENANT_C, None, canal_general["id"], "Oi", None)
        assert False, "deveria ter levantado NaoAutorizado"
    except NaoAutorizado:
        pass


def test_canal_inexistente_levanta_erro(db_session):
    try:
        sala_corporativa_service.listar_mensagens(db_session, TENANT_A, 9999)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
