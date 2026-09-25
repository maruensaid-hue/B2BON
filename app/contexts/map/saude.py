"""Saúde de conta (MAP) — score de risco de churn por conta.

Movido de `saude_conta_service` na Fase 1 para o contexto MAP; o serviço
antigo delega para cá. `conta` é qualquer objeto com `id`, `tenant_id` e
`criado_em` (o ORM `Conta` ou o DTO `OrganizationRef` do Shared Kernel).
`InteracaoConta` é dado do próprio MAP (sinais registrados pelo time).
"""

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.contexts.map import risk
from app.core.config import settings
from app.models.interacao_conta import InteracaoConta


class ContaAvaliavel(Protocol):
    id: int
    tenant_id: str
    criado_em: datetime


def listar_interacoes(db: Session, tenant_id: str, conta_id: int) -> list[InteracaoConta]:
    return (
        db.query(InteracaoConta)
        .filter_by(tenant_id=tenant_id, conta_id=conta_id)
        .order_by(InteracaoConta.criado_em.desc())
        .all()
    )


def classificar(score: float) -> str:
    return risk.classificar(score, settings.limiar_risco_critico_conta, settings.limiar_risco_atencao_conta)


def score_risco_conta(db: Session, conta: ContaAvaliavel) -> dict:
    interacoes = listar_interacoes(db, conta.tenant_id, conta.id)
    resultado = risk.calcular_score(interacoes, conta.criado_em)
    return {
        "conta_id": conta.id,
        "score": resultado["score"],
        "classificacao": classificar(resultado["score"]),
        "dias_sem_contato": resultado["dias_sem_contato"],
        "sinais": resultado["sinais"],
    }
