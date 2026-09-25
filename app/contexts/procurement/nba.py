"""Procurement Next Best Action (§45): sugestões a partir dos sinais de risco
e das pendências. Sugestão, nunca ato administrativo."""

from sqlalchemy.orm import Session

from app.models.demanda_compra import DemandaCompra

ACOES = {
    "CONTRACT_EXPIRING": "Considere iniciar o planejamento da contratação sucessora.",
    "INCOMPLETE_PLANNING": "Considere abrir o processo de contratação deste item do PCA.",
    "PROCESS_DELAY": "Revise o cronograma do processo e registre a justificativa do atraso.",
    "MISSING_DOCUMENTATION": "Anexe ao processo os documentos da etapa.",
    "PRICE_DEVIATION": "Revise a pesquisa de preços (número de amostras e cotações fora da faixa).",
    "DUPLICATE_PROCUREMENT": "Verifique se os processos semelhantes podem ser consolidados.",
    "BUDGET_MISMATCH": "Confira o alinhamento orçamentário com o PCA.",
    "SUPPLIER_CONCENTRATION": "Avalie ampliar a competitividade nesta categoria.",
    "REPEATED_AMENDMENTS": "Revise o histórico de aditivos antes de um novo.",
    "SLA_DETERIORATION": "Registre notificação ao fornecedor e intensifique a fiscalização.",
    "PROCUREMENT_FRAGMENTATION": "Avalie consolidar as contratações da categoria.",
}


def acoes(db: Session, tenant_id: str, resultado_riscos: dict) -> list[dict]:
    lista = [
        {"acao": ACOES[s["tipo"]], "motivo": s["mensagem"], "sinal": s["tipo"], "severidade": s["severidade"],
         "entidade_tipo": s["entidade_tipo"], "entidade_id": s["entidade_id"], "evidencia": s["evidencia"]}
        for s in resultado_riscos["sinais"] if s["tipo"] in ACOES
    ]
    pendentes = db.query(DemandaCompra).filter_by(tenant_id=tenant_id, status="ENVIADA").count()
    if pendentes:
        lista.append({"acao": "Analise as demandas enviadas pelas unidades.", "motivo": f"{pendentes} demanda(s) aguardando análise.",
                      "sinal": "DEMANDAS_PENDENTES", "severidade": "INFO", "entidade_tipo": "demanda_compra", "entidade_id": None,
                      "evidencia": {"quantidade": pendentes}})
    return lista
