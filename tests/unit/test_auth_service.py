from datetime import UTC, datetime, timedelta

import pytest

from app.models.convite_cadastro import ConviteCadastro
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service
from app.services.errors import NaoAutenticado, RegraNegocioViolada, ValidacaoFalhou

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


def _criar_licenca(db_session, tenant_id: str, max_usuarios: int, status: str = "ativa") -> Licenca:
    if db_session.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}"))
        db_session.flush()

    plano = Plano(
        nome=f"Plano teste {tenant_id}-{max_usuarios}",
        franquia_contas_mes=1000,
        max_usuarios=max_usuarios,
        preco_mensal=0.0,
    )
    db_session.add(plano)
    db_session.flush()

    licenca = Licenca(tenant_id=tenant_id, plano_id=plano.id, status=status)
    db_session.add(licenca)
    db_session.commit()
    return licenca


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
        db_session, convite.codigo, "Novo Usuário", "novo@teste.com.br", "senha123", aceite_termos=True
    )
    assert usuario.tenant_id == TENANT_ID
    assert usuario.papel == "user"
    assert usuario.termos_aceitos_em is not None

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Outro", "outro@teste.com.br", "senha123", aceite_termos=True
        )


def test_registro_sem_aceitar_termos_e_bloqueado(db_session):
    """Pedido do usuário: cadastro self-service (convite) precisa exigir o
    aceite da Política de Privacidade/Termos, com o momento gravado."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    with pytest.raises(ValidacaoFalhou):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Sem Aceite", "sem-aceite@teste.com.br", "senha123", aceite_termos=False
        )


def test_convite_revogado_bloqueia_registro(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "X", "x@teste.com.br", "senha123", aceite_termos=True
        )


def test_reativar_convite_revogado_volta_a_disponivel(db_session):
    """Pedido do usuário: revogar por engano ou mudar de ideia não pode
    obrigar a gerar um convite novo pra mesma pessoa."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    reativado = auth_service.reativar_convite(db_session, TENANT_ID, None, convite.codigo)

    assert reativado.status == "disponivel"
    usuario = auth_service.registrar_com_convite(
        db_session, convite.codigo, "Reaproveitado", "reaproveitado@teste.com.br", "senha123", aceite_termos=True
    )
    assert usuario.email == "reaproveitado@teste.com.br"


def test_reativar_convite_disponivel_falha(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        auth_service.reativar_convite(db_session, TENANT_ID, None, convite.codigo)


def test_excluir_convite_revogado(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    auth_service.excluir_convite(db_session, TENANT_ID, None, convite.codigo)

    assert db_session.query(ConviteCadastro).filter_by(codigo=convite.codigo).one_or_none() is None


def test_excluir_convite_disponivel_falha(db_session):
    """Nunca apagar um convite que alguém ainda possa usar."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        auth_service.excluir_convite(db_session, TENANT_ID, None, convite.codigo)


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
        auth_service.registrar_com_convite(
            db_session, "EXPIRADOTESTE", "X", "x2@teste.com.br", "senha123", aceite_termos=True
        )


def test_registro_com_email_ja_cadastrado_falha(db_session):
    _criar_usuario(db_session, email="existente@teste.com.br")
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Y", "existente@teste.com.br", "senha123", aceite_termos=True
        )


def test_gerar_convite_bloqueia_quando_limite_de_usuarios_atingido(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=1)
    _criar_usuario(db_session, email="unico@teste.com.br")

    with pytest.raises(RegraNegocioViolada):
        auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)


def test_gerar_convite_permite_quando_abaixo_do_limite(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=2)
    _criar_usuario(db_session, email="primeiro@teste.com.br")

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    assert convite.status == "disponivel"


def test_usuario_inativo_nao_conta_para_o_limite(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=1)
    _criar_usuario(db_session, email="inativo@teste.com.br", ativo=False)

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    assert convite.status == "disponivel"


def test_aceitar_convite_bloqueia_quando_limite_e_atingido_apos_convite_gerado(db_session):
    """O limite pode ser atingido por outro usuário depois que o convite já
    foi gerado — o bloqueio precisa valer também no aceite, não só na
    geração."""
    _criar_licenca(db_session, TENANT_ID, max_usuarios=2)
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    _criar_usuario(db_session, email="primeiro@teste.com.br")
    _criar_usuario(db_session, email="segundo@teste.com.br", papel="admin")

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Terceiro", "terceiro@teste.com.br", "senha123", aceite_termos=True
        )


def test_tenant_sem_licenca_ativa_nao_bloqueia_convite(db_session):
    """Tenant de convite-vitrine (Onda H) nasce sem `Licenca` de propósito
    — o limite de usuários por plano não se aplica a ele aqui."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    usuario = auth_service.registrar_com_convite(
        db_session, convite.codigo, "Sem Licença", "sem-licenca@teste.com.br", "senha123", aceite_termos=True
    )

    assert usuario.tenant_id == TENANT_ID


def test_licenca_suspensa_nao_bloqueia_convite(db_session):
    """Só a licença com status `ativa` é considerada — licença suspensa não
    tem plano aplicado (comportamento igual ao de `franquia_service`)."""
    _criar_licenca(db_session, TENANT_ID, max_usuarios=1, status="suspensa")
    _criar_usuario(db_session, email="unico@teste.com.br")

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    assert convite.status == "disponivel"
