from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cadencia import Cadencia
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def marcar_resposta(db: Session, tenant_id: str, decisor_id: int) -> dict:
    """Resposta detectada (E3-H3). Raio-X 2026-09-15: por padrão a resposta
    NÃO interrompe mais a cadência — uma resposta pedindo mais informação
    não é motivo pra parar de nutrir por e-mail/LinkedIn. Só cancela tudo
    se a própria cadência tiver `cancelar_ao_responder=True` (opção
    explícita, desligada por padrão). Mensagem avulsa (sem cadência, ex.:
    pedido de indicação) continua cancelando sempre — não tem flag pra
    checar, e é um pedido pontual mesmo. Cancelamento fino por mensagem
    individual continua disponível via `aprovacao_service.cancelar_mensagem`,
    independente disso."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")

    decisor.ultima_interacao_em = datetime.now(UTC)

    pendentes = (
        db.query(Mensagem)
        .outerjoin(Cadencia, Mensagem.cadencia_id == Cadencia.id)
        .filter(
            Mensagem.decisor_id == decisor.id,
            Mensagem.status.in_(["aguardando_aprovacao", "aprovado"]),
            or_(Mensagem.cadencia_id.is_(None), Cadencia.cancelar_ao_responder.is_(True)),
        )
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
