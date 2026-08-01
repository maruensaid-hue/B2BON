import pytest

from app.services import rampa_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-teste"


def test_rampa_aumenta_com_idade_do_canal():
    """E10-H1: rampa automática de volume por idade do canal."""
    limite_novo = rampa_service.limite_diario("whatsapp", dias_de_uso=1)
    limite_intermediario = rampa_service.limite_diario("whatsapp", dias_de_uso=10)
    limite_maduro = rampa_service.limite_diario("whatsapp", dias_de_uso=999)

    assert limite_novo < limite_intermediario < limite_maduro


def test_rampa_bloqueia_ao_exceder_limite_do_dia(db_session):
    """E10-H1: bloqueio de burla — assinante não consegue exceder o teto da rampa."""
    canal = "whatsapp"
    limite = rampa_service.limite_diario(canal, dias_de_uso=0)  # canal recém-criado

    for _ in range(limite):
        rampa_service.verificar_e_registrar(db_session, TENANT_ID, canal)

    with pytest.raises(RegraNegocioViolada):
        rampa_service.verificar_e_registrar(db_session, TENANT_ID, canal)


def test_rampa_e_isolada_por_canal(db_session):
    limite_whatsapp = rampa_service.limite_diario("whatsapp", dias_de_uso=0)
    for _ in range(limite_whatsapp):
        rampa_service.verificar_e_registrar(db_session, TENANT_ID, "whatsapp")

    # e-mail não é afetado pelo esgotamento do whatsapp
    rampa_service.verificar_e_registrar(db_session, TENANT_ID, "email")

    status_email = rampa_service.status_rampa(db_session, TENANT_ID, "email")
    assert status_email["usado_hoje"] == 1
