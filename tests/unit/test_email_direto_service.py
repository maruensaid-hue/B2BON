from datetime import time

import pytest

from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.email_direto import EmailDireto
from app.models.usuario import Usuario
from app.services import email_direto_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada
from tests.fakes import FakeEmailProvider

TENANT_ID = "tenant-teste"


@pytest.fixture()
def conta_e_decisor(db_session):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", email="decisor@teste.com")
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


@pytest.fixture()
def vendedor(db_session):
    usuario = Usuario(tenant_id=TENANT_ID, nome="Vendedor Teste", email="vendedor@teste.com", papel="user")
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_enviar_com_sucesso_persiste_email_e_atividade(db_session, conta_e_decisor, vendedor):
    conta, decisor = conta_e_decisor
    provider = FakeEmailProvider()

    resultado = email_direto_service.enviar(
        db_session, TENANT_ID, vendedor, decisor.id, "Assunto de teste", "Corpo da mensagem", provider
    )

    assert resultado["status"] == "enviado"
    assert resultado["conta_nome"] == conta.nome
    assert resultado["decisor_nome"] == decisor.nome
    assert len(provider.envios) == 1
    assert provider.envios[0]["destinatario"] == decisor.email
    assert "Corpo da mensagem" in provider.envios[0]["corpo"]
    assert "Para não receber mais e-mails" in provider.envios[0]["corpo"]

    email = db_session.query(EmailDireto).one()
    assert email.status == "enviado"
    assert email.conta_id == conta.id
    # Histórico guarda o texto EXATO que saiu (com o rodapé), não uma
    # reconstrução parcial do que o vendedor digitou.
    assert "Corpo da mensagem" in email.corpo
    assert "Para não receber mais e-mails" in email.corpo
    assert resultado["corpo"] == email.corpo


def test_enviar_decisor_sem_email_levanta_regra_negocio_violada(db_session, vendedor):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Sem Email", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Sem Email")
    db_session.add(decisor)
    db_session.commit()

    with pytest.raises(RegraNegocioViolada):
        email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", FakeEmailProvider())


def test_enviar_decisor_de_outro_tenant_levanta_nao_encontrado(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor

    with pytest.raises(NaoEncontrado):
        email_direto_service.enviar(db_session, "outro-tenant", vendedor, decisor.id, "Assunto", "Corpo", FakeEmailProvider())


def test_enviar_falha_do_provider_persiste_status_falhou_sem_levantar_excecao(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    provider = FakeEmailProvider()
    provider.falhar_proximos = 1

    resultado = email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert resultado["status"] == "falhou"
    assert resultado["motivo_falha"] == "falha simulada"
    email = db_session.query(EmailDireto).one()
    assert email.status == "falhou"
    assert email.enviado_em is None


def test_enviar_usa_assinatura_pessoal_quando_configurada(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    vendedor.email_assinatura = "Atenciosamente,\nVendedor Teste"
    db_session.commit()
    provider = FakeEmailProvider()

    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert "Atenciosamente" in provider.envios[0]["corpo"]


def test_enviar_cai_na_assinatura_do_tenant_quando_pessoal_nao_configurada(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    db_session.add(
        ConfiguracaoEnvio(
            tenant_id=TENANT_ID,
            remetente_nome="Empresa Teste",
            remetente_email="contato@empresateste.com",
            assinatura="Equipe Empresa Teste",
            horario_inicio=time(8, 0),
            horario_fim=time(18, 0),
        )
    )
    db_session.commit()
    provider = FakeEmailProvider()

    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert "Equipe Empresa Teste" in provider.envios[0]["corpo"]
    assert provider.envios[0]["remetente_email"] == "contato@empresateste.com"


def test_listar_enviados_usuario_comum_ve_so_os_proprios(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    outro_vendedor = Usuario(tenant_id=TENANT_ID, nome="Outro Vendedor", email="outro@teste.com", papel="user")
    db_session.add(outro_vendedor)
    db_session.commit()
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Meu e-mail", "Corpo", FakeEmailProvider())
    email_direto_service.enviar(db_session, TENANT_ID, outro_vendedor, decisor.id, "E-mail do outro", "Corpo", FakeEmailProvider())

    resultado = email_direto_service.listar_enviados(db_session, TENANT_ID, vendedor)

    assert len(resultado) == 1
    assert resultado[0]["assunto"] == "Meu e-mail"


def test_listar_enviados_admin_ve_todos(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    admin = Usuario(tenant_id=TENANT_ID, nome="Admin Teste", email="admin@teste.com", papel="admin")
    db_session.add(admin)
    db_session.commit()
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Meu e-mail", "Corpo", FakeEmailProvider())
    email_direto_service.enviar(db_session, TENANT_ID, admin, decisor.id, "E-mail do admin", "Corpo", FakeEmailProvider())

    resultado = email_direto_service.listar_enviados(db_session, TENANT_ID, admin)

    assert len(resultado) == 2


def test_configuracao_pessoal_get_e_set(db_session, vendedor):
    assert email_direto_service.obter_configuracao(vendedor) == {"email_nome_exibicao": None, "email_assinatura": None}

    resultado = email_direto_service.atualizar_configuracao(db_session, vendedor, "Vendedor Exibido", "Att, Vendedor")

    assert resultado == {"email_nome_exibicao": "Vendedor Exibido", "email_assinatura": "Att, Vendedor"}
