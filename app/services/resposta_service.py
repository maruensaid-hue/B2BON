from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def marcar_resposta(db: Session, tenant_id: str, decisor_id: int) -> dict:
    """Resposta detectada interrompe a cadência daquele contato em todos os
    canais (E3-H3). Chamada pelos webhooks de e-mail/WhatsApp — qualquer
    canal de resposta pausa todos os demais para o mesmo decisor."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    decisor.ultima_interacao_em = datetime.now(UTC)

    pendentes = (
        db.query(Mensagem)
        .filter(Mensagem.decisor_id == decisor.id, Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]))
        .all()
    )
    for mensagem in pendentes:
        mensagem.status = "cancelado"

    auditoria_service.registrar(
        db,
        tenant_id,
        "resposta_detectada",
        "decisor",
        decisor.id,
        None,
        {"mensagens_canceladas": len(pendentes)},
        conta_id=decisor.conta_id,
    )
    db.commit()
    return {"decisor_id": decisor.id, "mensagens_canceladas": len(pendentes)}
