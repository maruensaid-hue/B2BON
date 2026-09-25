"""Bid Workspace (Fase 9): tudo de uma licitação num lugar só."""

from sqlalchemy.orm import Session

from app.contexts.bids import conformidade, contratos, documentos, go_no_go, grafo, licitacoes, prazos
from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.decisao_go_no_go import DecisaoGoNoGo
from app.models.documento_licitacao import DocumentoLicitacao


def montar(db: Session, tenant_id: str, licitacao_id: int) -> dict:
    lic = licitacoes.obter(db, tenant_id, licitacao_id)
    matriz = conformidade.calcular(db, tenant_id, lic)
    decisoes = (
        db.query(DecisaoGoNoGo).filter_by(tenant_id=tenant_id, licitacao_id=lic.id).order_by(DecisaoGoNoGo.id.desc()).all()
    )
    return {
        "licitacao": licitacoes.como_dict(lic),
        "documentos": [
            documentos.como_dict(d)
            for d in db.query(DocumentoLicitacao).filter_by(tenant_id=tenant_id, licitacao_id=lic.id).order_by(DocumentoLicitacao.id)
        ],
        "requisitos": [licitacoes.requisito_dict(r) for r in licitacoes.listar_requisitos(db, tenant_id, lic.id)],
        "matriz_conformidade": matriz,
        "go_no_go": go_no_go.recomendar(db, tenant_id, lic, matriz),
        "decisoes": [
            {"id": d.id, "recomendacao": d.recomendacao, "decisao": d.decisao, "justificativa": d.justificativa,
             "decidido_por_usuario_id": d.decidido_por_usuario_id, "criado_em": d.criado_em}
            for d in decisoes
        ],
        "prazos": prazos.listar(db, tenant_id, licitacao_id=lic.id),
        "contratos": [contratos.como_dict(c) for c in db.query(ContratoVendaPublica).filter_by(tenant_id=tenant_id, licitacao_id=lic.id)],
        "grafo": grafo.da_licitacao(db, tenant_id, lic),
    }
