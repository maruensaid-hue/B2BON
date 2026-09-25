"""Saúde de conta (MAP) — score de risco de churn por conta.

Movido de `saude_conta_service` na Fase 1; na Fase 2 passa a ler as
interações pela porta `MapDataSource`, então o mesmo cálculo roda sobre
o CRM interno ou sobre qualquer `CrmAdapter` (modelo canônico).
`conta` é qualquer objeto com `id`, `tenant_id` e `criado_em` (o ORM
`Conta` ou o DTO `OrganizationRef`).
"""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.contexts.map import risk
from app.contexts.map.data_source import CrmInternoMapDataSource, MapDataSource
from app.core.config import settings


class ContaAvaliavel(Protocol):
    id: int | str
    tenant_id: str
    criado_em: datetime | None


def classificar(score: float) -> str:
    return risk.classificar(score, settings.limiar_risco_critico_conta, settings.limiar_risco_atencao_conta)


def score_risco(fonte: MapDataSource, conta: ContaAvaliavel) -> dict:
    interacoes = fonte.interacoes(conta.tenant_id, conta.id)
    resultado = risk.calcular_score(interacoes, conta.criado_em or datetime.now(UTC))
    return {
        "conta_id": conta.id,
        "score": resultado["score"],
        "classificacao": classificar(resultado["score"]),
        "dias_sem_contato": resultado["dias_sem_contato"],
        "sinais": resultado["sinais"],
    }


def score_risco_conta(db: Session, conta: ContaAvaliavel) -> dict:
    return score_risco(CrmInternoMapDataSource(db), conta)
