"""Parâmetros de custo das comissões para testes (D-074). Os valores são de teste — em produção o PO os informa."""

from datetime import date

from app.contexts.comissoes import contract as comissoes

INICIO = date(2000, 1, 1)


def definir_parametros(db, impostos: float = 0.0, infra: list[dict] | None = None, vigente_de: date = INICIO,
                       tipo_receita: str = "*") -> None:
    """Tax Profile com uma carga única de teste (OTHER_TAX sobre a receita) e Infrastructure Cost Model (padrão: percentual 0) vigentes desde `vigente_de`."""
    comissoes.tributos.criar(db, {"regime": "LUCRO_PRESUMIDO", "vigente_de": vigente_de, "tipo_receita": tipo_receita,
                                  "componentes": [{"tributo": "OTHER_TAX", "base": "RECEITA", "aliquota": impostos}]}, "teste")
    comissoes.infraestrutura.criar(db, {"nome": "Infra teste", "vigente_de": vigente_de,
                                        "componentes": infra or [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.0}]}, "teste")
    comissoes.motor.recalcular_aguardando(db)
    db.commit()
