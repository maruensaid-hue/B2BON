"""Sinais de relacionamento registrados no MAP (`InteracaoConta`)."""

from sqlalchemy.orm import Session

from app.models.interacao_conta import InteracaoConta


def listar_interacoes(db: Session, tenant_id: str, conta_id: int) -> list[InteracaoConta]:
    """Mais recente primeiro — é o que `risk.calcular_score` espera."""
    return (
        db.query(InteracaoConta)
        .filter_by(tenant_id=tenant_id, conta_id=conta_id)
        .order_by(InteracaoConta.criado_em.desc())
        .all()
    )
