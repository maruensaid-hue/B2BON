"""Procurement Process Workspace (§41): overview, demanda, planejamento,
documentos (ETP/TR), pesquisa de preços, aprovações, fornecedores,
esclarecimentos, eventos, contrato, tarefas, timeline, auditoria e AI
Insights (sinais + próxima ação)."""

from sqlalchemy.orm import Session

from app.contexts.procurement import cadastros, contratos, documentos, nba, precos, riscos
from app.models.auditoria import AuditLog
from app.models.contrato_compra import ContratoCompra
from app.models.demanda_compra import DemandaCompra
from app.models.documento_compras import DocumentoCompras
from app.models.evento_processo import EventoProcesso


def montar(db: Session, tenant_id: str, processo_id: int) -> dict:
    processo = cadastros.obter(db, tenant_id, "processo_contratacao", processo_id)
    demandas = (
        db.query(DemandaCompra).filter(DemandaCompra.tenant_id == tenant_id, DemandaCompra.id.in_(processo.demanda_ids or [-1])).all()
    )
    item = cadastros.obter(db, tenant_id, "item_pca", processo.item_pca_id) if processo.item_pca_id else None
    docs = db.query(DocumentoCompras).filter_by(tenant_id=tenant_id, processo_id=processo.id).order_by(DocumentoCompras.id).all()
    eventos = db.query(EventoProcesso).filter_by(tenant_id=tenant_id, processo_id=processo.id).order_by(EventoProcesso.id).all()
    contratos_do_processo = db.query(ContratoCompra).filter_by(tenant_id=tenant_id, processo_id=processo.id).all()
    sinais = riscos.sinais(db, tenant_id, processo_id=processo.id)
    auditoria = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant_id, AuditLog.entidade_tipo == "processo_contratacao", AuditLog.entidade_id == processo.id)
        .order_by(AuditLog.id)
        .all()
    )
    por_tipo = {t: [cadastros.como_dict(e) for e in eventos if e.tipo == t] for t in ("APROVACAO", "ESCLARECIMENTO", "TAREFA")}
    return {
        "overview": cadastros.como_dict(processo),
        "demandas": [cadastros.como_dict(d) for d in demandas],
        "planejamento": cadastros.como_dict(item) if item else None,
        "documentos": [documentos.como_dict(d) for d in docs],
        "estudos_tecnicos": [documentos.como_dict(d) for d in docs if d.tipo == "ETP"],
        "termos_de_referencia": [documentos.como_dict(d) for d in docs if d.tipo == "TR"],
        "pesquisa_precos": precos.resumo(db, tenant_id, processo.id),
        "aprovacoes": por_tipo["APROVACAO"],
        "esclarecimentos": por_tipo["ESCLARECIMENTO"],
        "tarefas": por_tipo["TAREFA"],
        "timeline": [cadastros.como_dict(e) for e in eventos],
        "fornecedores": sorted({c.fornecedor_id for c in contratos_do_processo}),
        "contrato": [contratos.inteligencia(db, tenant_id, c) for c in contratos_do_processo],
        "auditoria": [
            {"evento": a.evento_tipo, "ator_id": a.ator_id, "detalhes": a.detalhes, "em": a.criado_em} for a in auditoria
        ],
        "ai_insights": {"sinais": sinais, "proximas_acoes": nba.acoes(db, tenant_id, sinais)},
    }
