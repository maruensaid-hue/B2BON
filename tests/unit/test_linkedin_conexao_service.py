import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.usuario import Usuario
from app.services import linkedin_conexao_service
from app.services.errors import ValidacaoFalhou

TENANT_ID = "tenant-linkedin"

_CSV_EXPORT_LINKEDIN = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are blank."


First Name,Last Name,URL,Email Address,Company,Position,Connected On
Joao,Silva,https://www.linkedin.com/in/joao-silva,joao@example.com,Alpha Tech,CEO,01 Jan 2024
Maria,Souza,https://www.linkedin.com/in/maria-souza/,,Beta Clinica,Diretora,15 Mar 2023
"""


def _criar_usuario(db_session) -> Usuario:
    usuario = Usuario(tenant_id=TENANT_ID, nome="Vendedor Teste", email="vendedor@teste.com.br", papel="user", ativo=True)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def _criar_decisor(db_session, nome: str, linkedin_url: str | None = None) -> Decisor:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome=f"Empresa de {nome}", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome=nome, linkedin_url=linkedin_url)
    db_session.add(decisor)
    db_session.commit()
    return decisor


def test_importar_csv_acha_cabecalho_apos_notas_do_export_oficial(db_session):
    usuario = _criar_usuario(db_session)

    total = linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, _CSV_EXPORT_LINKEDIN)

    assert total == 2


def test_importar_csv_sem_cabecalho_reconhecivel_falha(db_session):
    usuario = _criar_usuario(db_session)

    with pytest.raises(ValidacaoFalhou):
        linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, "coluna_a,coluna_b\n1,2\n")


def test_reupload_substitui_conexoes_antigas(db_session):
    usuario = _criar_usuario(db_session)
    linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, _CSV_EXPORT_LINKEDIN)

    total = linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, _CSV_EXPORT_LINKEDIN)

    assert total == 2
    assert linkedin_conexao_service.status(db_session, TENANT_ID, usuario.id)["total"] == 2


def test_esta_conectado_por_url_com_variacao_de_protocolo_e_www(db_session):
    usuario = _criar_usuario(db_session)
    linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, _CSV_EXPORT_LINKEDIN)
    decisor = _criar_decisor(db_session, "Outro Nome", linkedin_url="http://www.linkedin.com/in/joao-silva/")

    assert linkedin_conexao_service.esta_conectado(db_session, TENANT_ID, usuario.id, decisor) is True


def test_esta_conectado_cai_para_nome_quando_decisor_sem_url(db_session):
    usuario = _criar_usuario(db_session)
    linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, _CSV_EXPORT_LINKEDIN)
    decisor = _criar_decisor(db_session, "maria souza")  # mesmo nome, caixa/acento diferentes

    assert linkedin_conexao_service.esta_conectado(db_session, TENANT_ID, usuario.id, decisor) is True


def test_esta_conectado_falso_quando_nao_ha_conexao_correspondente(db_session):
    usuario = _criar_usuario(db_session)
    linkedin_conexao_service.importar_csv(db_session, TENANT_ID, usuario.id, _CSV_EXPORT_LINKEDIN)
    decisor = _criar_decisor(db_session, "Pessoa Desconhecida")

    assert linkedin_conexao_service.esta_conectado(db_session, TENANT_ID, usuario.id, decisor) is False


def test_esta_conectado_falso_sem_nenhuma_conexao_importada(db_session):
    usuario = _criar_usuario(db_session)
    decisor = _criar_decisor(db_session, "Joao Silva")

    assert linkedin_conexao_service.esta_conectado(db_session, TENANT_ID, usuario.id, decisor) is False
