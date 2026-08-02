from datetime import UTC, datetime, timedelta

import pytest

from app.models.convite_cadastro import ConviteCadastro
from app.models.usuario import Usuario
from app.services import auth_service
from app.services.errors import NaoAutenticado, RegraNegocioViolada

TENANT_ID = "tenant-teste"


def _criar_usuario(db_session, **overrides) -> Usuario:
    dados = {
        "tenant_id": TENANT_ID,
        "nome": "Usuário Teste",
        "email": "usuario@teste.com.br",
        "senha_hash": auth_service.hash_senha("senha-forte-123"),
        "papel": "user",
        "ativo": True,
    }
    dados.update(overrides)
    usuario = Usuario(**dados)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_hash_e_verificacao_de_senha():
    hash_senha = auth_service.hash_senha("minha-senha")

    assert auth_service.verificar_senha("minha-senha", hash_senha)
    assert not auth_service.verificar_senha("senha-errada", hash_senha)


def test_gerar_e_validar_token(db_session):
    usuario = _criar_usuario(db_session)
    token = auth_service.gerar_token(usuario)

    validado = auth_service.validar_token(db_session, token)

    assert validado.id == usuario.id
    assert validado.tenant_id == usuario.tenant_id


def test_validar_token_invalido_levanta_nao_autenticado(db_session):
    with pytest.raises(NaoAutenticado):
        auth_service.validar_token(db_session, "token-forjado")


def test_validar_token_de_usuario_inativo_levanta_nao_autenticado(db_session):
    usuario = _criar_usuario(db_session, email="inativo@teste.com.br", ativo=False)
    token = auth_service.gerar_token(usuario)

    with pytest.raises(NaoAutenticado):
        auth_service.validar_token(db_session, token)


def test_autenticar_senha_incorreta_levanta_nao_autenticado(db_session):
    _criar_usuario(db_session, email="fulano@teste.com.br")

    with pytest.raises(NaoAutenticado):
        auth_service.autenticar_senha(db_session, "fulano@teste.com.br", "senha-errada")


def test_autenticar_senha_correta_atualiza_ultimo_login(db_session):
    _criar_usuario(db_session, email="fulano2@teste.com.br")

    usuario = auth_service.autenticar_senha(db_session, "fulano2@teste.com.br", "senha-forte-123")

    assert usuario.ultimo_login_em is not None


def test_fluxo_de_convite_gerar_usar_e_bloquear_reuso(db_session):
    """Onda A: convite pode ser usado uma única vez."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    assert convite.status == "disponivel"

    usuario = auth_service.registrar_com_convite(
        db_session, convite.codigo, "Novo Usuário", "novo@teste.com.br", "senha123"
    )
    assert usuario.tenant_id == TENANT_ID
    assert usuario.papel == "user"

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(db_session, convite.codigo, "Outro", "outro@teste.com.br", "senha123")


def test_convite_revogado_bloqueia_registro(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(db_session, convite.codigo, "X", "x@teste.com.br", "senha123")


def test_convite_expirado_bloqueia_registro(db_session):
    convite = ConviteCadastro(
        tenant_id=TENANT_ID,
        codigo="EXPIRADOTESTE",
        papel_concedido="user",
        validade_em=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(convite)
    db_session.commit()

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(db_session, "EXPIRADOTESTE", "X", "x2@teste.com.br", "senha123")


def test_registro_com_email_ja_cadastrado_falha(db_session):
    _criar_usuario(db_session, email="existente@teste.com.br")
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(db_session, convite.codigo, "Y", "existente@teste.com.br", "senha123")
