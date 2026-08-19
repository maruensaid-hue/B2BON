import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.convite_cadastro import ConviteCadastro
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoAutenticado, NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

PAPEIS_VALIDOS = {"super_admin", "admin", "user"}


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))


def gerar_token(usuario: Usuario) -> str:
    agora = datetime.now(UTC)
    payload = {
        "sub": str(usuario.id),
        "tenant_id": usuario.tenant_id,
        "papel": usuario.papel,
        "iat": agora,
        "exp": agora + timedelta(minutes=settings.jwt_expiracao_minutos),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def validar_token(db: Session, token: str) -> Usuario:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as erro:
        raise NaoAutenticado("Token inválido ou expirado.") from erro

    usuario = db.query(Usuario).filter_by(id=int(payload["sub"])).one_or_none()
    if usuario is None or not usuario.ativo:
        raise NaoAutenticado("Usuário não encontrado ou inativo.")
    return usuario


def autenticar_senha(db: Session, email: str, senha: str) -> Usuario:
    usuario = db.query(Usuario).filter_by(email=email).one_or_none()
    if usuario is None or usuario.senha_hash is None or not verificar_senha(senha, usuario.senha_hash):
        raise NaoAutenticado("E-mail ou senha inválidos.")
    if not usuario.ativo:
        raise NaoAutenticado("Usuário inativo.")

    usuario.ultimo_login_em = datetime.now(UTC)
    db.commit()
    db.refresh(usuario)
    return usuario


def autenticar_google(db: Session, id_token_str: str) -> Usuario:
    """Login via Google — só para e-mail já cadastrado por convite (Onda A).

    Não há auto-cadastro livre via Google: mantém o modelo de acesso por
    convite em todos os fluxos de entrada na plataforma.
    """
    if not settings.google_oauth_client_id:
        raise NaoAutenticado("Login via Google não está configurado.")
    try:
        info = google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), settings.google_oauth_client_id
        )
    except ValueError as erro:
        raise NaoAutenticado("Token do Google inválido.") from erro

    email = info.get("email")
    google_sub = info.get("sub")
    if not email or not google_sub:
        raise NaoAutenticado("Token do Google não contém e-mail verificado.")

    usuario = db.query(Usuario).filter_by(email=email).one_or_none()
    if usuario is None:
        raise NaoAutenticado("E-mail não cadastrado. Peça um convite antes de entrar com o Google.")
    if not usuario.ativo:
        raise NaoAutenticado("Usuário inativo.")

    if usuario.google_sub is None:
        usuario.google_sub = google_sub
    elif usuario.google_sub != google_sub:
        raise NaoAutenticado("Conta Google não corresponde ao cadastro.")

    usuario.ultimo_login_em = datetime.now(UTC)
    db.commit()
    db.refresh(usuario)
    return usuario


def _gerar_codigo_convite() -> str:
    return secrets.token_hex(8).upper()


def _verificar_limite_de_usuarios(db: Session, tenant_id: str) -> None:
    """Bloqueia convite/aceite quando o tenant já está no limite de
    usuários do plano da sua licença ativa.

    Tenant sem licença ativa (ex.: convite-vitrine da Onda H, que nasce
    deliberadamente sem `Licenca`) não tem limite de usuários aplicado
    aqui — a ausência de licença já restringe esse tenant a outros
    módulos, e criar uma segunda regra de bloqueio para o mesmo caso só
    duplicaria a intenção original.
    """
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id, status="ativa").one_or_none()
    if licenca is None:
        return
    plano = db.query(Plano).filter_by(id=licenca.plano_id).one_or_none()
    if plano is None:
        return

    usuarios_ativos = db.query(Usuario).filter_by(tenant_id=tenant_id, ativo=True).count()
    if usuarios_ativos >= plano.max_usuarios:
        raise RegraNegocioViolada(
            f"Limite de usuários do plano '{plano.nome}' atingido ({plano.max_usuarios}). "
            "Desative um usuário ou faça upgrade do plano antes de convidar outro."
        )


def gerar_convite(
    db: Session, tenant_id: str, ator_id: str | None, papel_concedido: str, validade_horas: int | None
) -> ConviteCadastro:
    if papel_concedido not in PAPEIS_VALIDOS:
        raise ValidacaoFalhou(f"Papel inválido: {papel_concedido}")
    _verificar_limite_de_usuarios(db, tenant_id)

    validade_em = datetime.now(UTC) + timedelta(hours=validade_horas) if validade_horas else None
    convite = ConviteCadastro(
        tenant_id=tenant_id,
        codigo=_gerar_codigo_convite(),
        papel_concedido=papel_concedido,
        criado_por_usuario_id=int(ator_id) if ator_id else None,
        validade_em=validade_em,
    )
    db.add(convite)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "convite_gerado", "convite_cadastro", convite.id, ator_id, {"papel_concedido": papel_concedido}
    )
    db.commit()
    db.refresh(convite)
    return convite


def revogar_convite(db: Session, tenant_id: str, ator_id: str | None, codigo: str) -> ConviteCadastro:
    convite = db.query(ConviteCadastro).filter_by(tenant_id=tenant_id, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "disponivel":
        raise RegraNegocioViolada("Só é possível revogar convites disponíveis.")

    convite.status = "revogado"
    auditoria_service.registrar(db, tenant_id, "convite_revogado", "convite_cadastro", convite.id, ator_id, {})
    db.commit()
    db.refresh(convite)
    return convite


def reativar_convite(db: Session, tenant_id: str, ator_id: str | None, codigo: str) -> ConviteCadastro:
    """Volta um convite revogado por engano pra "disponivel" — sem isto,
    revogar por engano ou mudar de ideia obrigava gerar um convite novo
    pra mesma pessoa (pedido do usuário: evitar acumular convites)."""
    convite = db.query(ConviteCadastro).filter_by(tenant_id=tenant_id, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "revogado":
        raise RegraNegocioViolada("Só é possível reativar convites revogados.")

    convite.status = "disponivel"
    auditoria_service.registrar(db, tenant_id, "convite_reativado", "convite_cadastro", convite.id, ator_id, {})
    db.commit()
    db.refresh(convite)
    return convite


def excluir_convite(db: Session, tenant_id: str, ator_id: str | None, codigo: str) -> None:
    """Remove um convite revogado da lista — só revogados, pra nunca
    apagar um convite que alguém ainda possa usar."""
    convite = db.query(ConviteCadastro).filter_by(tenant_id=tenant_id, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "revogado":
        raise RegraNegocioViolada("Só é possível excluir convites revogados.")

    auditoria_service.registrar(db, tenant_id, "convite_excluido", "convite_cadastro", convite.id, ator_id, {})
    db.delete(convite)
    db.commit()


def listar_convites(db: Session, tenant_id: str) -> list[ConviteCadastro]:
    return db.query(ConviteCadastro).filter_by(tenant_id=tenant_id).order_by(ConviteCadastro.id.desc()).all()


def _validar_convite_disponivel(db: Session, convite: ConviteCadastro | None, codigo: str) -> ConviteCadastro:
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status == "revogado":
        raise RegraNegocioViolada("Convite revogado.")
    if convite.status == "usado":
        raise RegraNegocioViolada("Convite já utilizado.")

    validade = convite.validade_em
    if validade is not None:
        if validade.tzinfo is None:
            validade = validade.replace(tzinfo=UTC)
        if validade < datetime.now(UTC):
            convite.status = "expirado"
            db.commit()
            raise RegraNegocioViolada("Convite expirado.")
    return convite


def registrar_com_convite(
    db: Session, codigo: str, nome: str, email: str, senha: str, aceite_termos: bool
) -> Usuario:
    if not aceite_termos:
        raise ValidacaoFalhou("É preciso aceitar a Política de Privacidade e os Termos de Uso para se cadastrar.")

    convite = db.query(ConviteCadastro).filter_by(codigo=codigo).one_or_none()
    convite = _validar_convite_disponivel(db, convite, codigo)

    if db.query(Usuario).filter_by(email=email).one_or_none() is not None:
        raise RegraNegocioViolada("E-mail já cadastrado.")
    _verificar_limite_de_usuarios(db, convite.tenant_id)

    usuario = Usuario(
        tenant_id=convite.tenant_id,
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        papel=convite.papel_concedido,
        termos_aceitos_em=datetime.now(UTC),
    )
    db.add(usuario)
    db.flush()

    convite.status = "usado"
    convite.usado_por_usuario_id = usuario.id

    auditoria_service.registrar(
        db, convite.tenant_id, "usuario_registrado_via_convite", "usuario", usuario.id, None, {"convite_codigo": codigo}
    )
    db.commit()
    db.refresh(usuario)
    return usuario
