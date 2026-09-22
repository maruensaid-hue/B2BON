from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.convite_cadastro import ConviteCadastro
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.redefinicao_senha import RedefinicaoSenha
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service
from app.services.errors import NaoAutenticado, NaoAutorizado, NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou
from tests.fakes import FakeEmailProvider

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


def _criar_licenca(db_session, tenant_id: str, max_usuarios: int | None, status: str = "ativa") -> Licenca:
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

    usuario, _primeiro_login = auth_service.autenticar_senha(db_session, "fulano2@teste.com.br", "senha-forte-123")

    assert usuario.ultimo_login_em is not None


def test_autenticar_senha_primeiro_login_true_so_na_primeira_vez(db_session):
    """Raio-X 2026-09-01: sinal usado pra disparar o tour guiado de
    onboarding uma única vez, sem campo novo no banco — reaproveita
    `ultimo_login_em` (nulo até o primeiro login de verdade)."""
    _criar_usuario(db_session, email="fulano3@teste.com.br")

    _usuario1, primeiro_login1 = auth_service.autenticar_senha(db_session, "fulano3@teste.com.br", "senha-forte-123")
    _usuario2, primeiro_login2 = auth_service.autenticar_senha(db_session, "fulano3@teste.com.br", "senha-forte-123")

    assert primeiro_login1 is True
    assert primeiro_login2 is False


def test_fluxo_de_convite_gerar_usar_e_bloquear_reuso(db_session):
    """Onda A: convite pode ser usado uma única vez."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)
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
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    with pytest.raises(ValidacaoFalhou):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Sem Aceite", "sem-aceite@teste.com.br", "senha123", aceite_termos=False
        )


def test_convite_revogado_bloqueia_registro(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "X", "x@teste.com.br", "senha123", aceite_termos=True
        )


def test_reativar_convite_revogado_volta_a_disponivel(db_session):
    """Pedido do usuário: revogar por engano ou mudar de ideia não pode
    obrigar a gerar um convite novo pra mesma pessoa."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    reativado = auth_service.reativar_convite(db_session, TENANT_ID, None, convite.codigo)

    assert reativado.status == "disponivel"
    usuario = auth_service.registrar_com_convite(
        db_session, convite.codigo, "Reaproveitado", "reaproveitado@teste.com.br", "senha123", aceite_termos=True
    )
    assert usuario.email == "reaproveitado@teste.com.br"


def test_reativar_convite_disponivel_falha(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        auth_service.reativar_convite(db_session, TENANT_ID, None, convite.codigo)


def test_excluir_convite_revogado(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)
    auth_service.revogar_convite(db_session, TENANT_ID, None, convite.codigo)

    auth_service.excluir_convite(db_session, TENANT_ID, None, convite.codigo)

    assert db_session.query(ConviteCadastro).filter_by(codigo=convite.codigo).one_or_none() is None


def test_excluir_convite_disponivel_falha(db_session):
    """Nunca apagar um convite que alguém ainda possa usar."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

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
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Y", "existente@teste.com.br", "senha123", aceite_termos=True
        )


def test_gerar_convite_bloqueia_quando_limite_de_usuarios_atingido(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=1)
    _criar_usuario(db_session, email="unico@teste.com.br")

    with pytest.raises(RegraNegocioViolada):
        auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)


def test_gerar_convite_permite_quando_abaixo_do_limite(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=2)
    _criar_usuario(db_session, email="primeiro@teste.com.br")

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    assert convite.status == "disponivel"


def test_gerar_convite_sem_limite_quando_plano_max_usuarios_e_nulo(db_session):
    """Raio-X 2026-09-22: plano "Teste" (free, só por convite) passa a ter
    `max_usuarios=NULL` — admin gratuito convida quantos vendedores
    precisar, sem nenhum teto."""
    _criar_licenca(db_session, TENANT_ID, max_usuarios=None)
    for numero in range(15):
        _criar_usuario(db_session, email=f"vendedor{numero}@teste.com.br")

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    assert convite.status == "disponivel"


def test_aceitar_convite_sem_limite_quando_plano_max_usuarios_e_nulo(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=None)
    for numero in range(15):
        _criar_usuario(db_session, email=f"vendedor{numero}@teste.com.br")
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    usuario = auth_service.registrar_com_convite(
        db_session, convite.codigo, "Vendedor 16", "vendedor16@teste.com.br", "senha123", aceite_termos=True
    )

    assert usuario.tenant_id == TENANT_ID


def test_gerar_convite_admin_comum_nao_pode_conceder_super_admin(db_session):
    """`exigir_papel("super_admin", "admin")` na rota só garante que quem
    chama é admin+ — sem esta trava, um admin comum podia gerar um
    convite com papel_concedido="super_admin" e se auto-elevar (super_admin
    é papel global, sem escopo de tenant)."""
    with pytest.raises(NaoAutorizado):
        auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "super_admin", validade_horas=24)


def test_gerar_convite_super_admin_pode_conceder_super_admin(db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "super_admin", "super_admin", validade_horas=24)

    assert convite.papel_concedido == "super_admin"


def test_usuario_inativo_nao_conta_para_o_limite(db_session):
    _criar_licenca(db_session, TENANT_ID, max_usuarios=1)
    _criar_usuario(db_session, email="inativo@teste.com.br", ativo=False)

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    assert convite.status == "disponivel"


def test_aceitar_convite_bloqueia_quando_limite_e_atingido_apos_convite_gerado(db_session):
    """O limite pode ser atingido por outro usuário depois que o convite já
    foi gerado — o bloqueio precisa valer também no aceite, não só na
    geração."""
    _criar_licenca(db_session, TENANT_ID, max_usuarios=2)
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)
    _criar_usuario(db_session, email="primeiro@teste.com.br")
    _criar_usuario(db_session, email="segundo@teste.com.br", papel="admin")

    with pytest.raises(RegraNegocioViolada):
        auth_service.registrar_com_convite(
            db_session, convite.codigo, "Terceiro", "terceiro@teste.com.br", "senha123", aceite_termos=True
        )


def test_tenant_sem_licenca_ativa_nao_bloqueia_convite(db_session):
    """Tenant de convite-vitrine (Onda H) nasce sem `Licenca` de propósito
    — o limite de usuários por plano não se aplica a ele aqui."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    usuario = auth_service.registrar_com_convite(
        db_session, convite.codigo, "Sem Licença", "sem-licenca@teste.com.br", "senha123", aceite_termos=True
    )

    assert usuario.tenant_id == TENANT_ID


def test_licenca_suspensa_nao_bloqueia_convite(db_session):
    """Só a licença com status `ativa` é considerada — licença suspensa não
    tem plano aplicado (comportamento igual ao de `franquia_service`)."""
    _criar_licenca(db_session, TENANT_ID, max_usuarios=1, status="suspensa")
    _criar_usuario(db_session, email="unico@teste.com.br")

    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "admin", "user", validade_horas=24)

    assert convite.status == "disponivel"


def test_solicitar_redefinicao_senha_cria_token_e_envia_email(db_session):
    _criar_usuario(db_session, email="esqueci@teste.com.br")
    fake_email = FakeEmailProvider()

    auth_service.solicitar_redefinicao_senha(db_session, "esqueci@teste.com.br", fake_email)

    redefinicao = db_session.query(RedefinicaoSenha).one()
    assert redefinicao.status == "disponivel"
    assert len(fake_email.envios) == 1
    assert redefinicao.token in fake_email.envios[0]["corpo"]
    assert fake_email.envios[0]["destinatario"] == "esqueci@teste.com.br"


def test_solicitar_redefinicao_senha_email_inexistente_nao_envia_nem_falha(db_session):
    """Nunca revela se o e-mail existe (evita enumeração de contas) —
    chamar com um e-mail que não existe não levanta erro nenhum."""
    fake_email = FakeEmailProvider()

    auth_service.solicitar_redefinicao_senha(db_session, "ninguem@teste.com.br", fake_email)

    assert fake_email.envios == []
    assert db_session.query(RedefinicaoSenha).count() == 0


def test_solicitar_redefinicao_senha_usuario_so_google_nao_envia(db_session):
    """Sem `senha_hash` (login só por Google) não há senha pra redefinir."""
    _criar_usuario(db_session, email="so-google@teste.com.br", senha_hash=None, google_sub="google-sub-123")
    fake_email = FakeEmailProvider()

    auth_service.solicitar_redefinicao_senha(db_session, "so-google@teste.com.br", fake_email)

    assert fake_email.envios == []


def test_solicitar_redefinicao_senha_pedido_novo_invalida_token_anterior(db_session):
    _criar_usuario(db_session, email="dois-pedidos@teste.com.br")
    fake_email = FakeEmailProvider()

    auth_service.solicitar_redefinicao_senha(db_session, "dois-pedidos@teste.com.br", fake_email)
    primeiro_token = db_session.query(RedefinicaoSenha).filter_by(status="disponivel").one().token

    auth_service.solicitar_redefinicao_senha(db_session, "dois-pedidos@teste.com.br", fake_email)

    primeiro = db_session.query(RedefinicaoSenha).filter_by(token=primeiro_token).one()
    assert primeiro.status == "expirado"
    assert db_session.query(RedefinicaoSenha).filter_by(status="disponivel").count() == 1


def test_redefinir_senha_com_token_valido_troca_a_senha(db_session):
    usuario = _criar_usuario(db_session, email="trocar@teste.com.br")
    senha_hash_antiga = usuario.senha_hash
    auth_service.solicitar_redefinicao_senha(db_session, "trocar@teste.com.br", FakeEmailProvider())
    token = db_session.query(RedefinicaoSenha).one().token

    auth_service.redefinir_senha(db_session, token, "senha-nova-123")

    db_session.refresh(usuario)
    assert usuario.senha_hash != senha_hash_antiga
    assert auth_service.verificar_senha("senha-nova-123", usuario.senha_hash)
    redefinicao = db_session.query(RedefinicaoSenha).filter_by(token=token).one()
    assert redefinicao.status == "usado"


def test_redefinir_senha_token_ja_usado_falha(db_session):
    _criar_usuario(db_session, email="reuso@teste.com.br")
    auth_service.solicitar_redefinicao_senha(db_session, "reuso@teste.com.br", FakeEmailProvider())
    token = db_session.query(RedefinicaoSenha).one().token
    auth_service.redefinir_senha(db_session, token, "senha-nova-123")

    with pytest.raises(RegraNegocioViolada):
        auth_service.redefinir_senha(db_session, token, "outra-senha-456")


def test_redefinir_senha_token_expirado_falha(db_session):
    usuario = _criar_usuario(db_session, email="expirado@teste.com.br")
    redefinicao = RedefinicaoSenha(
        usuario_id=usuario.id, token="token-expirado", validade_em=datetime.now(UTC) - timedelta(hours=1)
    )
    db_session.add(redefinicao)
    db_session.commit()

    with pytest.raises(RegraNegocioViolada):
        auth_service.redefinir_senha(db_session, "token-expirado", "senha-nova-123")


def test_redefinir_senha_token_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        auth_service.redefinir_senha(db_session, "token-que-nunca-existiu", "senha-nova-123")


def test_autenticar_google_sem_client_id_configurado_falha(db_session, monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "")

    with pytest.raises(NaoAutenticado):
        auth_service.autenticar_google(db_session, "qualquer-id-token")


def test_autenticar_google_token_invalido_falha(db_session, monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "client-id-teste")

    def _verificar_falha(*args, **kwargs):
        raise ValueError("assinatura inválida")

    monkeypatch.setattr(auth_service.google_id_token, "verify_oauth2_token", _verificar_falha)

    with pytest.raises(NaoAutenticado):
        auth_service.autenticar_google(db_session, "token-forjado")


def test_autenticar_google_email_nao_cadastrado_falha(db_session, monkeypatch):
    """Sem auto-cadastro via Google (Onda A) — só entra quem já foi
    convidado por e-mail antes."""
    monkeypatch.setattr(settings, "google_oauth_client_id", "client-id-teste")
    monkeypatch.setattr(
        auth_service.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"email": "novo@teste.com.br", "sub": "google-sub-1"},
    )

    with pytest.raises(NaoAutenticado):
        auth_service.autenticar_google(db_session, "token-valido")


def test_autenticar_google_primeiro_login_vincula_google_sub(db_session, monkeypatch):
    usuario = _criar_usuario(db_session, email="ja-cadastrado@teste.com.br")
    assert usuario.google_sub is None
    monkeypatch.setattr(settings, "google_oauth_client_id", "client-id-teste")
    monkeypatch.setattr(
        auth_service.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"email": "ja-cadastrado@teste.com.br", "sub": "google-sub-novo"},
    )

    usuario_logado, primeiro_login = auth_service.autenticar_google(db_session, "token-valido")

    assert usuario_logado.id == usuario.id
    assert usuario_logado.google_sub == "google-sub-novo"
    assert primeiro_login is True


def test_autenticar_google_sub_diferente_do_cadastrado_falha(db_session, monkeypatch):
    """Uma conta Google já vinculada não pode ser trocada por outra
    silenciosamente."""
    _criar_usuario(db_session, email="conta-google@teste.com.br", google_sub="google-sub-original")
    monkeypatch.setattr(settings, "google_oauth_client_id", "client-id-teste")
    monkeypatch.setattr(
        auth_service.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"email": "conta-google@teste.com.br", "sub": "google-sub-outro"},
    )

    with pytest.raises(NaoAutenticado):
        auth_service.autenticar_google(db_session, "token-valido")


def test_autenticar_google_usuario_inativo_falha(db_session, monkeypatch):
    _criar_usuario(db_session, email="inativo-google@teste.com.br", ativo=False)
    monkeypatch.setattr(settings, "google_oauth_client_id", "client-id-teste")
    monkeypatch.setattr(
        auth_service.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"email": "inativo-google@teste.com.br", "sub": "google-sub-x"},
    )

    with pytest.raises(NaoAutenticado):
        auth_service.autenticar_google(db_session, "token-valido")
