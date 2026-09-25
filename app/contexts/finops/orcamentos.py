"""Budgets e quotas de IA por tenant/módulo/feature (Fase 5).

Janela: mês corrente (UTC). `BLOQUEAR` faz o gateway recusar a chamada
antes de chamar o provedor; `ALERTAR` só sinaliza (dashboard). Budget em
créditos (Fase 15) fica em `limites.verificar_orcamento`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.orcamento_ia import OrcamentoIa
from app.models.registro_uso_ia import RegistroUsoIa
from app.services.errors import ValidacaoFalhou

ESCOPOS = frozenset({"tenant", "modulo", "feature"})
ACOES = frozenset({"ALERTAR", "BLOQUEAR"})


@dataclass(frozen=True)
class EstadoOrcamento:
    orcamento_id: int
    escopo: str
    alvo: str | None
    acao: str
    custo_usd: Decimal
    chamadas: int
    limite_custo_usd: Decimal | None
    limite_chamadas: int | None
    percentual: float | None
    estourado: bool
    em_alerta: bool


def _inicio_mes() -> datetime:
    agora = datetime.now(UTC)
    return datetime(agora.year, agora.month, 1)


def uso_no_mes(db: Session, tenant_id: str, escopo: str = "tenant", alvo: str | None = None) -> tuple[Decimal, int]:
    query = db.query(func.coalesce(func.sum(RegistroUsoIa.custo_usd), 0), func.count(RegistroUsoIa.id)).filter(
        RegistroUsoIa.tenant_id == tenant_id,
        RegistroUsoIa.status == "sucesso",
        RegistroUsoIa.criado_em >= _inicio_mes(),
    )
    if escopo == "modulo":
        query = query.filter(RegistroUsoIa.modulo == alvo)
    elif escopo == "feature":
        query = query.filter(RegistroUsoIa.feature == alvo)
    custo, chamadas = query.one()
    return Decimal(str(custo or 0)), int(chamadas or 0)


def criar(db: Session, tenant_id: str, dados: dict) -> OrcamentoIa:
    if dados.get("escopo", "tenant") not in ESCOPOS or dados.get("acao", "ALERTAR") not in ACOES:
        raise ValidacaoFalhou("Escopo ou ação inválidos.")
    if dados.get("escopo") in ("modulo", "feature") and not dados.get("alvo"):
        raise ValidacaoFalhou("Escopo modulo/feature exige `alvo`.")
    if dados.get("limite_custo_usd") is None and dados.get("limite_chamadas") is None:
        raise ValidacaoFalhou("Informe limite_custo_usd ou limite_chamadas.")
    orcamento = OrcamentoIa(tenant_id=tenant_id, **dados)
    db.add(orcamento)
    db.commit()
    db.refresh(orcamento)
    return orcamento


def estados(db: Session, tenant_id: str) -> list[EstadoOrcamento]:
    resultado = []
    for orcamento in db.query(OrcamentoIa).filter_by(tenant_id=tenant_id, ativo=True).all():
        custo, chamadas = uso_no_mes(db, tenant_id, orcamento.escopo, orcamento.alvo)
        limite_custo = Decimal(str(orcamento.limite_custo_usd)) if orcamento.limite_custo_usd is not None else None
        razoes = []
        if limite_custo:
            razoes.append(float(custo / limite_custo))
        if orcamento.limite_chamadas:
            razoes.append(chamadas / orcamento.limite_chamadas)
        percentual = max(razoes) * 100 if razoes else None
        resultado.append(
            EstadoOrcamento(
                orcamento_id=orcamento.id, escopo=orcamento.escopo, alvo=orcamento.alvo, acao=orcamento.acao,
                custo_usd=custo, chamadas=chamadas, limite_custo_usd=limite_custo, limite_chamadas=orcamento.limite_chamadas,
                percentual=percentual, estourado=percentual is not None and percentual >= 100,
                em_alerta=percentual is not None and percentual >= orcamento.percentual_alerta,
            )
        )
    return resultado


def motivo_de_bloqueio(db: Session, tenant_id: str, modulo: str, feature: str) -> str | None:
    """`None` = pode chamar. Senão, o motivo (vai para o ledger como `bloqueado`)."""
    for estado in estados(db, tenant_id):
        aplica = estado.escopo == "tenant" or (estado.escopo == "modulo" and estado.alvo == modulo) or (estado.escopo == "feature" and estado.alvo == feature)
        if aplica and estado.acao == "BLOQUEAR" and estado.estourado:
            return f"orçamento de IA ({estado.escopo}{':' + estado.alvo if estado.alvo else ''}) atingido no mês"
    # Saldo de créditos: desde a Fase 15 é checado na reserva da execução
    # (`execucoes.abrir`), não aqui.
    return None
