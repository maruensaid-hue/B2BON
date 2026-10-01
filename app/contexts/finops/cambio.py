"""Câmbio (OI-018; D-075 tabela, D-076 política). Nenhuma cotação no código.

Política (D-076): fonte BANCO_CENTRAL_DO_BRASIL, PTAX de fechamento (`PTAX_CLOSE`), par USD/BRL, cotação de venda. A
cotação aplicável a um custo é a PTAX de fechamento do dia útil da contabilização; sem PTAX nesse dia, a última PTAX de
fechamento anterior. Cada cotação guarda o snapshot (taxa, data, fonte, momento da obtenção) e é usada como foi gravada:
um custo já fechado não é recalculado quando chega cotação nova.

    AI_COST_BRL = AI_COST_USD × cotação USD/BRL aplicável

A PTAX é obtida da API pública do Banco Central (rotina horária e botão no Admin) ou cadastrada pelo Financeiro. Sem
cotação, o valor em reais é desconhecido (AWAITING_FX_RATE) — nunca estimado.
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models.cotacao_cambio import CotacaoCambio
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

logger = logging.getLogger(__name__)

AGUARDANDO = "AWAITING_FX_RATE"
POLITICA = {"fonte": "BANCO_CENTRAL_DO_BRASIL", "tipo": "PTAX_CLOSE", "par": "USD/BRL", "lado": "VENDA",
            "regra": "PTAX de fechamento do dia útil da contabilização; sem PTAX no dia, a última anterior"}
URL_PTAX = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)"
            "?@dataCotacao='{data}'&$format=json")
DIAS_RETROATIVOS = 7


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def aplicavel(db: Session, base: str = "USD", cotacao: str = "BRL", em: datetime | None = None) -> CotacaoCambio | None:
    return (db.query(CotacaoCambio).filter(CotacaoCambio.moeda_base == base, CotacaoCambio.moeda_cotacao == cotacao,
                                           CotacaoCambio.vigente_em <= (em or _agora()))
            .order_by(CotacaoCambio.vigente_em.desc(), CotacaoCambio.id.desc()).first())


def taxa(db: Session, base: str = "USD", cotacao: str = "BRL", em: datetime | None = None) -> Decimal | None:
    linha = aplicavel(db, base, cotacao, em)
    return Decimal(str(linha.taxa)) if linha else None


def snapshot(linha: CotacaoCambio) -> dict:
    """fx_rate, fx_date, source, retrieved_at — guardado junto do custo convertido."""
    return {"fx_rate": float(linha.taxa), "fx_date": (linha.data_cotacao or linha.vigente_em.date()).isoformat(), "source": linha.fonte,
            "type": linha.tipo, "retrieved_at": (linha.obtida_em or linha.criado_em or linha.vigente_em).isoformat()}


def registrar(db: Session, dados: dict, ator_id: str | None) -> CotacaoCambio:
    base, cotacao = (dados.get("moeda_base") or "").upper(), (dados.get("moeda_cotacao") or "").upper()
    if len(base) != 3 or len(cotacao) != 3 or base == cotacao:
        raise ValidacaoFalhou("Informe o par de moedas (ex.: USD/BRL).")
    if dados.get("taxa") is None or Decimal(str(dados["taxa"])) <= 0:
        raise ValidacaoFalhou("Cotação precisa ser positiva.")
    if not (dados.get("fonte") or "").strip():
        raise ValidacaoFalhou("Informe a fonte da cotação (ex.: PTAX de fechamento do Banco Central).")
    tipo = dados.get("tipo") or "MANUAL"
    if tipo not in ("MANUAL", POLITICA["tipo"]):
        raise ValidacaoFalhou("Tipo de cotação: MANUAL ou PTAX_CLOSE.")
    data_cotacao = dados.get("data_cotacao")
    vigente_em = dados.get("vigente_em") or (datetime.combine(data_cotacao, datetime.min.time()) if data_cotacao else _agora())
    linha = CotacaoCambio(moeda_base=base, moeda_cotacao=cotacao, taxa=Decimal(str(dados["taxa"])), fonte=dados["fonte"].strip(),
                          vigente_em=vigente_em, tipo=tipo, data_cotacao=data_cotacao or vigente_em.date(),
                          obtida_em=dados.get("obtida_em") or _agora(), criado_por=ator_id)
    db.add(linha)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "cotacao_cambio_registrada", "cotacao_cambio", linha.id, ator_id,
                                {"par": f"{base}/{cotacao}", "taxa": str(linha.taxa), "fonte": linha.fonte, "tipo": tipo,
                                 "data_cotacao": linha.data_cotacao.isoformat(), "vigente_em": linha.vigente_em.isoformat(),
                                 "origem": "admin" if ator_id else "rotina"})
    return linha


def _buscar_ptax_bcb(dia: date) -> Decimal | None:
    """PTAX de fechamento (venda) do dia na API pública do Banco Central; None em dia sem boletim."""
    resposta = httpx.get(URL_PTAX.format(data=dia.strftime("%m-%d-%Y")), timeout=10)
    resposta.raise_for_status()
    valores = resposta.json().get("value") or []
    return Decimal(str(valores[-1]["cotacaoVenda"])) if valores else None


def sincronizar_ptax(db: Session, hoje: date | None = None, buscar: Callable[[date], Decimal | None] | None = None) -> dict:
    """Grava as PTAX de fechamento dos últimos dias úteis que ainda não estão na tabela (idempotente). Falha de rede não
    derruba a rotina: o custo sem cotação continua AWAITING_FX_RATE."""
    hoje, buscar = hoje or _agora().date(), buscar or _buscar_ptax_bcb
    gravadas, erro = [], None
    for atraso in range(DIAS_RETROATIVOS, -1, -1):
        dia = hoje - timedelta(days=atraso)
        if dia.weekday() >= 5 or db.query(CotacaoCambio).filter_by(tipo=POLITICA["tipo"], moeda_base="USD", moeda_cotacao="BRL",
                                                                    data_cotacao=dia).first():
            continue
        try:
            valor = buscar(dia)
        except Exception as exc:  # noqa: BLE001 — rede/API indisponível: tenta de novo na próxima rotina
            erro = str(exc)[:200]
            logger.warning("PTAX indisponível para %s: %s", dia, erro)
            break
        if valor is not None:
            registrar(db, {"moeda_base": "USD", "moeda_cotacao": "BRL", "taxa": valor, "fonte": POLITICA["fonte"], "tipo": POLITICA["tipo"],
                           "data_cotacao": dia}, None)
            gravadas.append(dia.isoformat())
    db.commit()
    return {"gravadas": gravadas, "erro": erro}


def como_dict(linha: CotacaoCambio) -> dict:
    return {"id": linha.id, "moeda_base": linha.moeda_base, "moeda_cotacao": linha.moeda_cotacao, "taxa": float(linha.taxa),
            "fonte": linha.fonte, "tipo": linha.tipo, "data_cotacao": linha.data_cotacao.isoformat() if linha.data_cotacao else None,
            "vigente_em": linha.vigente_em.isoformat(), "obtida_em": linha.obtida_em.isoformat() if linha.obtida_em else None}
