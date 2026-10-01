"""Parâmetros de custo das comissões para testes (D-074, D-076). Os valores são de teste — em produção o PO os informa."""

from datetime import date

from app.contexts.comissoes import contract as comissoes
from app.models.plano import Plano

INICIO = date(2000, 1, 1)


def componente(custo_referencia: float = 0.0, **extra) -> dict:
    """Componente do Infrastructure Cost Pool (mensal, em reais, plano máximo) com valores de teste."""
    return {"fornecedor": "Fornecedor teste", "servico": "Hospedagem", "categoria": "HOSTING", "plano": "Pro", "plano_referencia": "Max",
            "ciclo_cobranca": "MONTHLY", "moeda": "BRL", "custo_referencia": custo_referencia, "politica_custo": "MAX_CONTRACTED_PLAN",
            "metodo_alocacao": "WEIGHTED", "contabilizacao": "INFRASTRUCTURE", "vigente_de": INICIO, **extra}


def definir_parametros(db, impostos: float = 0.0, pool: list[dict] | None = None, vigente_de: date = INICIO,
                       tipo_receita: str = "*", tier_padrao: str | None = "ENTRY") -> None:
    """Tax Profile com uma carga única de teste (OTHER_TAX sobre a receita) e Infrastructure Cost Pool (padrão: um componente
    de custo 0) vigentes desde `vigente_de`. Planos sem tier recebem `tier_padrao`, para entrarem na alocação ponderada."""
    comissoes.tributos.criar(db, {"regime": "LUCRO_PRESUMIDO", "vigente_de": vigente_de, "tipo_receita": tipo_receita,
                                  "componentes": [{"tributo": "OTHER_TAX", "base": "RECEITA", "aliquota": impostos}]}, "teste")
    for dados in pool or [componente()]:
        comissoes.infraestrutura.criar(db, {**dados, "vigente_de": dados.get("vigente_de", vigente_de)}, "teste")
    if tier_padrao:
        for plano in db.query(Plano).filter(Plano.tier_infraestrutura.is_(None)).all():
            plano.tier_infraestrutura = tier_padrao
    db.flush()
    comissoes.motor.recalcular_aguardando(db)
    db.commit()
