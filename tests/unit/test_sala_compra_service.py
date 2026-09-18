from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.services import rede_social_service, sala_compra_service, sala_corporativa_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def _conectar(db_session, tenant_a, tenant_b):
    conexao = rede_social_service.solicitar_conexao(db_session, tenant_a, None, tenant_b)
    rede_social_service.responder_conexao(db_session, tenant_b, None, conexao.id, aceitar=True)


def _criar_negocio(db_session, tenant_id, **overrides) -> Negocio:
    conta = Conta(tenant_id=tenant_id, nome="Conta Teste", status="priorizada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    estagio = EstagioFunil(tenant_id=tenant_id, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    dados = {
        "tenant_id": tenant_id, "conta_id": conta.id, "decisor_id": decisor.id, "estagio_id": estagio.id,
        "nome": "Negócio Teste", "valor": 1000.0, "probabilidade": 50, "origem": "manual",
    }
    dados.update(overrides)
    negocio = Negocio(**dados)
    db_session.add(negocio)
    db_session.commit()
    return negocio


def _abrir_sala(db_session, tenant_a, tenant_b) -> dict:
    _conectar(db_session, tenant_a, tenant_b)
    return sala_corporativa_service.abrir_ou_obter_sala(db_session, tenant_a, None, tenant_b)


def test_vincular_negocio_a_sala(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    negocio = _criar_negocio(db_session, TENANT_A)

    vinculo = sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio.id, False)

    assert vinculo["negocio_id"] == negocio.id
    assert vinculo["negocio_nome"] == "Negócio Teste"
    assert vinculo["estagio_nome"] == "Descoberta"
    assert vinculo["e_vendedor"] is True


def test_negocio_de_outro_tenant_nao_pode_ser_vinculado(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    negocio_de_b = _criar_negocio(db_session, TENANT_B)

    try:
        sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio_de_b.id, False)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_comprador_nao_ve_negocio_quando_nao_visivel(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    negocio = _criar_negocio(db_session, TENANT_A)
    sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio.id, False)

    visto_pelo_vendedor = sala_compra_service.obter_para_sala(db_session, TENANT_A, sala["id"])
    visto_pelo_comprador = sala_compra_service.obter_para_sala(db_session, TENANT_B, sala["id"])

    assert visto_pelo_vendedor is not None
    assert visto_pelo_comprador is None


def test_comprador_ve_negocio_quando_visivel(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    negocio = _criar_negocio(db_session, TENANT_A)
    sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio.id, True)

    visto_pelo_comprador = sala_compra_service.obter_para_sala(db_session, TENANT_B, sala["id"])

    assert visto_pelo_comprador is not None
    assert visto_pelo_comprador["e_vendedor"] is False


def test_outro_lado_nao_pode_vincular_outro_negocio(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    negocio_a = _criar_negocio(db_session, TENANT_A)
    negocio_b = _criar_negocio(db_session, TENANT_B)
    sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio_a.id, False)

    try:
        sala_compra_service.vincular_negocio(db_session, TENANT_B, None, sala["id"], negocio_b.id, False)
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_vendedor_pode_atualizar_o_proprio_vinculo(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    negocio = _criar_negocio(db_session, TENANT_A)
    sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio.id, False)

    atualizado = sala_compra_service.vincular_negocio(db_session, TENANT_A, None, sala["id"], negocio.id, True)

    assert atualizado["visivel_para_comprador"] is True


def test_sem_vinculo_retorna_none(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)

    assert sala_compra_service.obter_para_sala(db_session, TENANT_A, sala["id"]) is None


def test_canal_interno_nao_aparece_pra_quem_nao_criou(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    sala_corporativa_service.criar_canal(db_session, TENANT_A, None, sala["id"], "LEGAL", None, "interno")

    canais_de_a = sala_corporativa_service.listar_canais(db_session, TENANT_A, sala["id"])
    canais_de_b = sala_corporativa_service.listar_canais(db_session, TENANT_B, sala["id"])

    assert any(c["tipo"] == "LEGAL" for c in canais_de_a)
    assert not any(c["tipo"] == "LEGAL" for c in canais_de_b)


def test_mensagem_em_canal_interno_de_outro_tenant_e_negada(db_session):
    sala = _abrir_sala(db_session, TENANT_A, TENANT_B)
    canal = sala_corporativa_service.criar_canal(db_session, TENANT_A, None, sala["id"], "LEGAL", None, "interno")

    try:
        sala_corporativa_service.enviar_mensagem_sala(db_session, TENANT_B, None, canal["id"], "Oi", None)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
