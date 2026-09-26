"""Contract Intelligence — buy side (§47): saldo, execução, aditivos, desempenho."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.contrato_compra import ContratoCompra
from app.models.evento_contrato_compra import EventoContratoCompra


def inteligencia(db: Session, tenant_id: str, contrato: ContratoCompra, hoje: date | None = None) -> dict:
    return inteligencia_em_lote(db, tenant_id, [contrato], hoje)[contrato.id]


def inteligencia_em_lote(db: Session, tenant_id: str, contratos: list[ContratoCompra], hoje: date | None = None) -> dict[int, dict]:
    """Inteligência de vários contratos com os eventos numa consulta (Phase D, TD-090)."""
    eventos: dict[int, list[EventoContratoCompra]] = {c.id: [] for c in contratos}
    if contratos:
        consulta = db.query(EventoContratoCompra).filter(EventoContratoCompra.tenant_id == tenant_id,
                                                         EventoContratoCompra.contrato_id.in_(list(eventos)))
        for e in consulta.order_by(EventoContratoCompra.data, EventoContratoCompra.id):
            eventos[e.contrato_id].append(e)
    return {c.id: _inteligencia(c, eventos[c.id], hoje or date.today()) for c in contratos}


def _inteligencia(contrato: ContratoCompra, eventos: list[EventoContratoCompra], hoje: date) -> dict:
    pago = sum(e.valor or 0 for e in eventos if e.tipo == "PAGAMENTO")
    aditivos = [e for e in eventos if e.tipo == "ADITIVO"]
    notas = [e.nota for e in eventos if e.tipo == "FISCALIZACAO" and e.nota is not None]
    return {
        "contrato_id": contrato.id,
        "valor_inicial": contrato.valor_inicial,
        "valor_atual": contrato.valor_atual,
        "pago": pago,
        "saldo": (contrato.valor_atual - pago) if contrato.valor_atual is not None else None,
        "percentual_executado": round(pago / contrato.valor_atual, 3) if contrato.valor_atual else None,
        "dias_para_fim": (contrato.vigencia_fim - hoje).days if contrato.vigencia_fim else None,
        "aditivos": len(aditivos),
        "acrescimo_percentual": (
            round(contrato.valor_atual / contrato.valor_inicial - 1, 3)
            if contrato.valor_inicial and contrato.valor_atual is not None else None
        ),
        "fiscalizacoes": len(notas),
        "nota_media": round(sum(notas) / len(notas), 2) if notas else None,
        "ocorrencias": sum(1 for e in eventos if e.tipo == "OCORRENCIA"),
        "entregas": sum(1 for e in eventos if e.tipo == "ENTREGA"),
        "eventos": [
            {"id": e.id, "tipo": e.tipo, "descricao": e.descricao, "valor": e.valor, "nota": e.nota, "data": e.data} for e in eventos
        ],
    }
