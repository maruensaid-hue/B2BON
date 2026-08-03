from app.models.usuario import Usuario
from app.providers.rede_social.nucleo import NucleoRedeSocialProvider

TENANT_ID = "tenant-teste"


def test_eh_assinante_true_para_email_de_usuario_existente(db_session):
    db_session.add(Usuario(tenant_id=TENANT_ID, nome="Fulano", email="fulano@empresa.com.br", papel="user", ativo=True))
    db_session.commit()

    provider = NucleoRedeSocialProvider(db_session)

    assert provider.eh_assinante("fulano@empresa.com.br") is True


def test_eh_assinante_false_para_email_desconhecido(db_session):
    provider = NucleoRedeSocialProvider(db_session)

    assert provider.eh_assinante("ninguem@empresa.com.br") is False
