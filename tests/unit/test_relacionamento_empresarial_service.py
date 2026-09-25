import pytest

from app.services import relacionamento_empresarial_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

pytestmark = pytest.mark.usefixtures("tenants_da_rede")

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def test_declarar_relacionamento(db_session):
    relacionamento = relacionamento_empresarial_service.declarar(
        db_session, TENANT_A, "usuario-1", TENANT_B, "SUPPLIER_OF", "publica"
    )

    assert relacionamento["tenant_id_origem"] == TENANT_A
    assert relacionamento["tenant_id_destino"] == TENANT_B
    assert relacionamento["tipo"] == "SUPPLIER_OF"
    assert relacionamento["confianca"] == "autodeclarada"
    assert relacionamento["pode_confirmar"] is False  # quem declarou não confirma o próprio


def test_declarar_com_proprio_tenant_falha(db_session):
    try:
        relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_A, "SUPPLIER_OF", "publica")
        assert False, "deveria ter levantado ValidacaoFalhou"
    except ValidacaoFalhou:
        pass


def test_declarar_tipo_invalido_falha(db_session):
    try:
        relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "TIPO_INVALIDO", "publica")
        assert False, "deveria ter levantado ValidacaoFalhou"
    except ValidacaoFalhou:
        pass


def test_contraparte_confirma_relacionamento(db_session):
    relacionamento = relacionamento_empresarial_service.declarar(
        db_session, TENANT_A, None, TENANT_B, "PARTNER_OF", "publica"
    )

    confirmado = relacionamento_empresarial_service.confirmar(db_session, TENANT_B, "usuario-b", relacionamento["id"])

    assert confirmado["confianca"] == "confirmada_pela_contraparte"


def test_quem_nao_e_contraparte_nao_pode_confirmar(db_session):
    relacionamento = relacionamento_empresarial_service.declarar(
        db_session, TENANT_A, None, TENANT_B, "PARTNER_OF", "publica"
    )

    try:
        relacionamento_empresarial_service.confirmar(db_session, TENANT_C, None, relacionamento["id"])
        assert False, "deveria ter levantado NaoAutorizado"
    except NaoAutorizado:
        pass


def test_listar_da_empresa_ve_relacionamentos_como_origem_e_destino(db_session):
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "SUPPLIER_OF", "publica")
    relacionamento_empresarial_service.declarar(db_session, TENANT_C, None, TENANT_A, "CUSTOMER_OF", "publica")

    resultado = relacionamento_empresarial_service.listar_da_empresa(db_session, TENANT_A, TENANT_A)

    assert len(resultado) == 2
    tipos = {item["tipo"] for item in resultado}
    assert tipos == {"SUPPLIER_OF", "CUSTOMER_OF"}


def test_listar_da_empresa_terceiro_so_ve_publicos(db_session):
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "SUPPLIER_OF", "privada")
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_C, "PARTNER_OF", "publica")

    resultado = relacionamento_empresarial_service.listar_da_empresa(db_session, TENANT_C, TENANT_A)

    assert len(resultado) == 1
    assert resultado[0]["tipo"] == "PARTNER_OF"


def test_listar_da_empresa_a_propria_ve_todos_mesmo_privados(db_session):
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "SUPPLIER_OF", "privada")

    resultado = relacionamento_empresarial_service.listar_da_empresa(db_session, TENANT_A, TENANT_A)

    assert len(resultado) == 1


def test_remover_relacionamento(db_session):
    relacionamento = relacionamento_empresarial_service.declarar(
        db_session, TENANT_A, None, TENANT_B, "SUPPLIER_OF", "publica"
    )

    relacionamento_empresarial_service.remover(db_session, TENANT_A, None, relacionamento["id"])

    assert relacionamento_empresarial_service.listar_da_empresa(db_session, TENANT_A, TENANT_A) == []


def test_remover_por_quem_nao_e_origem_falha(db_session):
    relacionamento = relacionamento_empresarial_service.declarar(
        db_session, TENANT_A, None, TENANT_B, "SUPPLIER_OF", "publica"
    )

    try:
        relacionamento_empresarial_service.remover(db_session, TENANT_B, None, relacionamento["id"])
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_empresa_citada_nao_ve_aresta_privada_declarada_sobre_ela(db_session):
    """D-027: antes a listagem da própria empresa trazia as arestas privadas
    que OUTRA empresa declarou sobre ela."""
    relacionamento_empresarial_service.declarar(db_session, TENANT_A, None, TENANT_B, "LOOKING_FOR", "privada")

    assert relacionamento_empresarial_service.listar_da_empresa(db_session, TENANT_B, TENANT_B) == []
    assert len(relacionamento_empresarial_service.listar_da_empresa(db_session, TENANT_A, TENANT_A)) == 1
