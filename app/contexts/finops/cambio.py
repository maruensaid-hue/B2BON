"""Câmbio (OI-018, D-075): cotações informadas pelo Financeiro, com fonte e vigência. Nunca há cotação no código.

    AI_COST_BRL = AI_COST_USD × cotação USD/BRL aplicável (a mais recente com vigência até o instante do custo)

Sem cotação, o custo em reais é desconhecido (AWAITING_FX_RATE) — nunca estimado.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cotacao_cambio import CotacaoCambio
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

AGUARDANDO = "AWAITING_FX_RATE"


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def aplicavel(db: Session, base: str = "USD", cotacao: str = "BRL", em: datetime | None = None) -> CotacaoCambio | None:
    return (db.query(CotacaoCambio).filter(CotacaoCambio.moeda_base == base, CotacaoCambio.moeda_cotacao == cotacao,
                                           CotacaoCambio.vigente_em <= (em or _agora()))
            .order_by(CotacaoCambio.vigente_em.desc(), CotacaoCambio.id.desc()).first())


def taxa(db: Session, base: str = "USD", cotacao: str = "BRL", em: datetime | None = None) -> Decimal | None:
    linha = aplicavel(db, base, cotacao, em)
    return Decimal(str(linha.taxa)) if linha else None


def registrar(db: Session, dados: dict, ator_id: str | None) -> CotacaoCambio:
    base, cotacao = (dados.get("moeda_base") or "").upper(), (dados.get("moeda_cotacao") or "").upper()
    if len(base) != 3 or len(cotacao) != 3 or base == cotacao:
        raise ValidacaoFalhou("Informe o par de moedas (ex.: USD/BRL).")
    if dados.get("taxa") is None or Decimal(str(dados["taxa"])) <= 0:
        raise ValidacaoFalhou("Cotação precisa ser positiva.")
    if not (dados.get("fonte") or "").strip():
        raise ValidacaoFalhou("Informe a fonte da cotação (ex.: PTAX venda do Banco Central).")
    linha = CotacaoCambio(moeda_base=base, moeda_cotacao=cotacao, taxa=Decimal(str(dados["taxa"])), fonte=dados["fonte"].strip(),
                          vigente_em=dados.get("vigente_em") or _agora(), criado_por=ator_id)
    db.add(linha)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "cotacao_cambio_registrada", "cotacao_cambio", linha.id, ator_id,
                                {"par": f"{base}/{cotacao}", "taxa": str(linha.taxa), "fonte": linha.fonte,
                                 "vigente_em": linha.vigente_em.isoformat(), "origem": "admin"})
    return linha


def como_dict(linha: CotacaoCambio) -> dict:
    return {"id": linha.id, "moeda_base": linha.moeda_base, "moeda_cotacao": linha.moeda_cotacao, "taxa": float(linha.taxa),
            "fonte": linha.fonte, "vigente_em": linha.vigente_em.isoformat()}
