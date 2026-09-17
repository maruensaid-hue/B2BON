from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.notificacao_rede_social import NotificacaoRedeSocial

_LIMITE_PADRAO = 50


def criar(db: Session, tenant_id: str, tipo: str, referencia_tipo: str, referencia_id: int, mensagem: str) -> None:
    """Helper interno de wiring (master prompt §65) — chamado de dentro
    de outras transações (solicitar_conexao, responder_conexao, comentar,
    reagir, enviar_mensagem); não comita, o `flush` garante o id/ordem
    sem fechar a transação de quem chamou."""
    db.add(
        NotificacaoRedeSocial(
            tenant_id=tenant_id,
            tipo=tipo,
            referencia_tipo=referencia_tipo,
            referencia_id=referencia_id,
            mensagem=mensagem,
        )
    )
    db.flush()


def _serializar(notificacao: NotificacaoRedeSocial) -> dict:
    return {
        "id": notificacao.id,
        "tipo": notificacao.tipo,
        "referencia_tipo": notificacao.referencia_tipo,
        "referencia_id": notificacao.referencia_id,
        "mensagem": notificacao.mensagem,
        "lida": notificacao.lida_em is not None,
        "criado_em": notificacao.criado_em,
    }


def listar(db: Session, tenant_id: str, limite: int = _LIMITE_PADRAO) -> list[dict]:
    notificacoes = (
        db.query(NotificacaoRedeSocial)
        .filter_by(tenant_id=tenant_id)
        .order_by(NotificacaoRedeSocial.criado_em.desc(), NotificacaoRedeSocial.id.desc())
        .limit(limite)
        .all()
    )
    return [_serializar(notificacao) for notificacao in notificacoes]


def marcar_lida(db: Session, tenant_id: str, notificacao_id: int) -> None:
    notificacao = db.query(NotificacaoRedeSocial).filter_by(id=notificacao_id, tenant_id=tenant_id).one_or_none()
    if notificacao is None:
        return
    if notificacao.lida_em is None:
        notificacao.lida_em = func.now()
        db.commit()


def marcar_todas_lidas(db: Session, tenant_id: str) -> None:
    (
        db.query(NotificacaoRedeSocial)
        .filter_by(tenant_id=tenant_id, lida_em=None)
        .update({"lida_em": func.now()})
    )
    db.commit()


def contar_nao_lidas(db: Session, tenant_id: str) -> int:
    return db.query(func.count(NotificacaoRedeSocial.id)).filter_by(tenant_id=tenant_id, lida_em=None).scalar() or 0
