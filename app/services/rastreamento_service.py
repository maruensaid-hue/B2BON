import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mensagem import Mensagem
from app.services.errors import ValidacaoFalhou

_SEPARADOR = ":"

# PNG transparente 1x1 — o pixel de rastreio em si, servido pelo endpoint
# público. Não depende de nenhuma lib de imagem, é um arquivo válido fixo.
PIXEL_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d763f8ffff3f0005fe02fea739669d0000000049454e"
    "44ae426082"
)


def gerar_token_abertura(tenant_id: str, mensagem_id: int) -> str:
    """Mesmo padrão HMAC stateless do token de opt-out
    (`optout_service.gerar_token`) — sem tabela própria."""
    payload = f"{tenant_id}{_SEPARADOR}{mensagem_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def _validar_token(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de rastreio inválido.")
    tenant_id, mensagem_id_str, assinatura = partes
    try:
        mensagem_id = int(mensagem_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de rastreio inválido.") from erro

    esperado = gerar_token_abertura(tenant_id, mensagem_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de rastreio inválido.")
    return tenant_id, mensagem_id


def url_pixel(tenant_id: str, mensagem_id: int) -> str:
    token = gerar_token_abertura(tenant_id, mensagem_id)
    return f"{settings.url_base_api}/webhooks/email/aberto/{token}.png"


def registrar_abertura(db: Session, token: str) -> None:
    """Endpoint público (imagem carregada pelo cliente de e-mail do
    destinatário) — token inválido não deve derrubar a imagem nem vazar
    detalhe do motivo, só não registra nada (E-mails automatizados/scanners
    de segurança às vezes disparam requisições malformadas de propósito)."""
    try:
        tenant_id, mensagem_id = _validar_token(token)
    except ValidacaoFalhou:
        return

    mensagem = db.query(Mensagem).filter_by(id=mensagem_id, tenant_id=tenant_id).one_or_none()
    if mensagem is None or mensagem.aberto_em is not None:
        return

    mensagem.aberto_em = datetime.now(UTC)
    db.commit()
