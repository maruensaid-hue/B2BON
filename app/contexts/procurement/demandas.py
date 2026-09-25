"""Demand intelligence (§40), determinística e sempre sujeita a revisão humana:
duplicidade, processos similares, contratos existentes, informações que
faltam e sugestão de consolidação."""

from sqlalchemy.orm import Session

from app.contexts.shared.texto import termos_em_comum
from app.models.contrato_compra import ContratoCompra
from app.models.demanda_compra import DemandaCompra
from app.models.processo_contratacao import ProcessoContratacao

ABERTAS = ("RASCUNHO", "ENVIADA", "EM_ANALISE", "APROVADA")
CAMPOS_ESSENCIAIS = {
    "justificativa": "Justificativa da necessidade",
    "categoria": "Categoria",
    "valor_estimado": "Valor estimado",
    "data_necessaria": "Data em que é necessária",
    "referencia_orcamentaria": "Referência orçamentária",
}


def analisar(db: Session, tenant_id: str, demanda: DemandaCompra) -> dict:
    outras = db.query(DemandaCompra).filter(
        DemandaCompra.tenant_id == tenant_id, DemandaCompra.id != demanda.id, DemandaCompra.status.in_(ABERTAS)
    ).all()
    duplicatas = [
        {"demanda_id": d.id, "necessidade": d.necessidade, "termos_em_comum": sorted(comuns)}
        for d in outras if (comuns := termos_em_comum(demanda.necessidade, d.necessidade))
    ]
    mesma_categoria = [d for d in outras if demanda.categoria and d.categoria == demanda.categoria]
    processos = [
        {"processo_id": p.id, "objeto": p.objeto, "status": p.status}
        for p in db.query(ProcessoContratacao).filter_by(tenant_id=tenant_id).all()
        if termos_em_comum(demanda.necessidade, p.objeto)
    ]
    contratos = [
        {"contrato_id": c.id, "objeto": c.objeto, "vigencia_fim": c.vigencia_fim}
        for c in db.query(ContratoCompra).filter_by(tenant_id=tenant_id, status="VIGENTE").all()
        if termos_em_comum(demanda.necessidade, c.objeto)
    ]
    faltando = [rotulo for campo, rotulo in CAMPOS_ESSENCIAIS.items() if getattr(demanda, campo) in (None, "")]
    consolidacao = None
    if mesma_categoria:
        valores = [d.valor_estimado for d in [demanda, *mesma_categoria]]
        consolidacao = {
            "categoria": demanda.categoria,
            "demandas": [demanda.id, *[d.id for d in mesma_categoria]],
            "valor_total_estimado": sum(valores) if all(v is not None for v in valores) else None,
            "motivo": "Demandas abertas da mesma categoria podem ser atendidas por um único processo.",
        }
    return {
        "demanda_id": demanda.id,
        "possiveis_duplicidades": duplicatas,
        "processos_similares": processos,
        "contratos_existentes": contratos,
        "informacoes_faltantes": faltando,
        "sugestao_consolidacao": consolidacao,
        "aviso": "Sugestões analíticas para revisão humana; não são decisão.",
    }
