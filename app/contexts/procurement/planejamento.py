"""Procurement Planning dashboard (§39)."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.contexts.procurement.tipos import STATUS_PROCESSO_FINAIS
from app.models.contrato_compra import ContratoCompra
from app.models.demanda_compra import DemandaCompra
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.item_pca import ItemPca
from app.models.plano_contratacao import PlanoContratacao
from app.models.processo_contratacao import ProcessoContratacao

DIAS_PROXIMAS = 90


def painel(db: Session, tenant_id: str, plano: PlanoContratacao, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    itens = db.query(ItemPca).filter_by(tenant_id=tenant_id, plano_id=plano.id).all()
    ids_itens = [i.id for i in itens]
    processos = db.query(ProcessoContratacao).filter(
        ProcessoContratacao.tenant_id == tenant_id, ProcessoContratacao.item_pca_id.in_(ids_itens or [-1])
    ).all()
    ids_processos = [p.id for p in processos]
    contratos = db.query(ContratoCompra).filter(
        ContratoCompra.tenant_id == tenant_id, ContratoCompra.processo_id.in_(ids_processos or [-1])
    ).all()
    pagamentos = db.query(EventoContratoCompra).filter(
        EventoContratoCompra.tenant_id == tenant_id, EventoContratoCompra.tipo == "PAGAMENTO",
        EventoContratoCompra.contrato_id.in_([c.id for c in contratos] or [-1]),
    ).all()

    planejado = sum(i.valor_estimado or 0 for i in itens if i.status != "CANCELADO")
    comprometido = sum(p.valor_estimado or 0 for p in processos if p.status not in STATUS_PROCESSO_FINAIS)
    contratado = sum(c.valor_atual or 0 for c in contratos)
    executado = sum(e.valor or 0 for e in pagamentos)
    atrasados = [
        {"processo_id": p.id, "objeto": p.objeto, "prazo_previsto": p.prazo_previsto, "status": p.status}
        for p in processos
        if p.prazo_previsto and p.prazo_previsto < hoje and p.status not in STATUS_PROCESSO_FINAIS
    ]
    em_risco = [
        {"demanda_id": d.id, "necessidade": d.necessidade, "data_necessaria": d.data_necessaria}
        for d in db.query(DemandaCompra).filter(
            DemandaCompra.tenant_id == tenant_id, DemandaCompra.item_pca_id.in_(ids_itens or [-1]),
            DemandaCompra.status.in_(("ENVIADA", "EM_ANALISE", "APROVADA")),
        ).all()
        if d.data_necessaria and d.data_necessaria <= hoje + timedelta(days=60)
    ]
    proximas = [
        {"item_pca_id": i.id, "descricao": i.descricao, "data_prevista": i.data_prevista, "valor_estimado": i.valor_estimado}
        for i in itens
        if i.status == "PLANEJADO" and i.data_prevista and hoje <= i.data_prevista <= hoje + timedelta(days=DIAS_PROXIMAS)
    ]
    return {
        "plano_id": plano.id,
        "ano": plano.ano,
        "valor_planejado": planejado,
        "comprometido": comprometido,
        "contratado": contratado,
        "executado": executado,
        "percentual_execucao": round(executado / contratado, 3) if contratado else None,
        "processos_atrasados": atrasados,
        "demandas_em_risco": em_risco,
        "proximas_contratacoes": proximas,
    }
