from app.services import seguidor_empresa_service
from app.services.errors import ValidacaoFalhou

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def test_seguir_e_esta_seguindo(db_session):
    seguidor_empresa_service.seguir(db_session, TENANT_A, None, TENANT_B)

    assert seguidor_empresa_service.esta_seguindo(db_session, TENANT_A, TENANT_B) is True
    assert seguidor_empresa_service.esta_seguindo(db_session, TENANT_B, TENANT_A) is False


def test_seguir_o_proprio_tenant_falha(db_session):
    try:
        seguidor_empresa_service.seguir(db_session, TENANT_A, None, TENANT_A)
        assert False, "deveria ter levantado ValidacaoFalhou"
    except ValidacaoFalhou:
        pass


def test_seguir_duas_vezes_e_idempotente(db_session):
    primeiro = seguidor_empresa_service.seguir(db_session, TENANT_A, None, TENANT_B)
    segundo = seguidor_empresa_service.seguir(db_session, TENANT_A, None, TENANT_B)

    assert primeiro.id == segundo.id
    assert len(seguidor_empresa_service.seguindo(db_session, TENANT_A)) == 1


def test_deixar_de_seguir(db_session):
    seguidor_empresa_service.seguir(db_session, TENANT_A, None, TENANT_B)

    seguidor_empresa_service.deixar_de_seguir(db_session, TENANT_A, None, TENANT_B)

    assert seguidor_empresa_service.esta_seguindo(db_session, TENANT_A, TENANT_B) is False


def test_deixar_de_seguir_quem_nunca_seguiu_e_idempotente(db_session):
    seguidor_empresa_service.deixar_de_seguir(db_session, TENANT_A, None, TENANT_B)  # não deve levantar erro


def test_seguidores_de(db_session):
    seguidor_empresa_service.seguir(db_session, TENANT_A, None, TENANT_B)
    seguidor_empresa_service.seguir(db_session, "tenant-c", None, TENANT_B)

    assert set(seguidor_empresa_service.seguidores_de(db_session, TENANT_B)) == {TENANT_A, "tenant-c"}
