import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

_SEPARADOR = ":"


def gerar_token(tenant_id: str, decisor_id: int) -> str:
    """Token de opt-out assinado (HMAC) — sem tabela própria, verificável
    de forma stateless a partir de `settings.secret_key`."""
    payload = f"{tenant_id}{_SEPARADOR}{decisor_id}"
    assinatura = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}{_SEPARADOR}{assinatura}"


def _validar_token(token: str) -> tuple[str, int]:
    partes = token.split(_SEPARADOR)
    if len(partes) != 3:
        raise ValidacaoFalhou("Token de opt-out inválido.")
    tenant_id, decisor_id_str, assinatura = partes
    try:
        decisor_id = int(decisor_id_str)
    except ValueError as erro:
        raise ValidacaoFalhou("Token de opt-out inválido.") from erro

    esperado = gerar_token(tenant_id, decisor_id).rsplit(_SEPARADOR, 1)[-1]
    if not hmac.compare_digest(assinatura, esperado):
        raise ValidacaoFalhou("Token de opt-out inválido.")
    return tenant_id, decisor_id


def _cancelar_mensagens_pendentes(db: Session, decisor_id: int) -> int:
    pendentes = (
        db.query(Mensagem)
        .filter(Mensagem.decisor_id == decisor_id, Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]))
        .all()
    )
    for mensagem in pendentes:
        mensagem.status = "cancelado"
    return len(pendentes)


def processar_por_token(db: Session, token: str) -> dict:
    """Opt-out via link do e-mail — endpoint público, sem X-Tenant-Id (E9-H2)."""
    tenant_id, decisor_id = _validar_token(token)
    return processar(db, tenant_id, decisor_id, origem="email")


def processar(db: Session, tenant_id: str, decisor_id: int, origem: str) -> dict:
    """Efeito imediato em todos os canais e cadências do assinante,
    supressão permanente (E9-H2)."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    if decisor.suprimido_em is None:
        decisor.suprimido_em = datetime.now(UTC)

    canceladas = _cancelar_mensagens_pendentes(db, decisor.id)

    auditoria_service.registrar(
        db,
        tenant_id,
        "optout_registrado",
        "decisor",
        decisor.id,
        None,
        {"origem": origem, "mensagens_canceladas": canceladas},
        conta_id=decisor.conta_id,
    )
    db.commit()
    return {"decisor_id": decisor.id, "suprimido": True, "mensagens_canceladas": canceladas}


def existe_supressao(db: Session, decisor_id: int) -> bool:
    """Lista de supressão consultada antes de qualquer novo envio (E9-H2)."""
    decisor = db.query(Decisor).filter_by(id=decisor_id).one_or_none()
    return decisor is not None and decisor.suprimido_em is not None
