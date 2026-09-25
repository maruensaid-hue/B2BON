"""Procurement Graph foundation (Fase 9, §43), lado vendedor.

Grafo derivado (sem tabela nova, D-024): nós e arestas no vocabulário do
modelo canônico de procurement (PublicOrganization → ProcurementProcess →
Lot/Item → BID → Result → PublicContract), montados a partir das tabelas do
tenant. O lado comprador (Fase 10) usa a mesma forma com seus próprios
dados, sem cruzar a barreira Buy/Sell.
"""

from sqlalchemy.orm import Session

from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.requisito_licitacao import RequisitoLicitacao


def da_licitacao(db: Session, tenant_id: str, licitacao: Licitacao) -> dict:
    nos: list[dict] = []
    arestas: list[dict] = []
    org = f"org:{licitacao.orgao_cnpj or licitacao.orgao_nome or 'desconhecido'}"
    processo = f"processo:{licitacao.id}"
    lance = f"bid:{licitacao.id}:{tenant_id}"
    nos += [
        {"id": org, "tipo": "PUBLIC_ORGANIZATION", "nome": licitacao.orgao_nome, "cnpj": licitacao.orgao_cnpj},
        {"id": processo, "tipo": "PROCUREMENT_PROCESS", "nome": licitacao.titulo, "modalidade": licitacao.modalidade,
         "fonte": licitacao.fonte, "fonte_url": licitacao.fonte_url},
        {"id": lance, "tipo": "BID", "status": licitacao.status, "valor": licitacao.valor_proposta},
    ]
    arestas += [{"de": org, "para": processo, "tipo": "RUNS"}, {"de": lance, "para": processo, "tipo": "SUBMITTED_TO"}]

    for doc in db.query(DocumentoLicitacao).filter_by(tenant_id=tenant_id, licitacao_id=licitacao.id).all():
        no = f"documento:{doc.id}"
        nos.append({"id": no, "tipo": "PROCUREMENT_DOCUMENT", "kind": doc.tipo, "nome": doc.nome_arquivo, "sha256": doc.sha256})
        arestas.append({"de": processo, "para": no, "tipo": "HAS_DOCUMENT"})
    for req in db.query(RequisitoLicitacao).filter(
        RequisitoLicitacao.tenant_id == tenant_id, RequisitoLicitacao.licitacao_id == licitacao.id,
        RequisitoLicitacao.categoria.in_(("LOTE", "ITEM")), RequisitoLicitacao.status != "descartado",
    ).all():
        no = f"{req.categoria.lower()}:{req.id}"
        nos.append({"id": no, "tipo": "LOT" if req.categoria == "LOTE" else "ITEM", "descricao": req.descricao,
                    "evidencia": {"documento_id": req.documento_id, "pagina": req.pagina}})
        arestas.append({"de": processo, "para": no, "tipo": "HAS_" + ("LOT" if req.categoria == "LOTE" else "ITEM")})

    if licitacao.status in ("GANHA", "PERDIDA"):
        resultado = f"resultado:{licitacao.id}"
        nos.append({"id": resultado, "tipo": "RESULT", "vencedor": licitacao.vencedor, "status": licitacao.status})
        arestas += [{"de": processo, "para": resultado, "tipo": "HAS_RESULT"}, {"de": lance, "para": resultado, "tipo": licitacao.status}]
    for c in db.query(ContratoVendaPublica).filter_by(tenant_id=tenant_id, licitacao_id=licitacao.id).all():
        no = f"contrato:{c.id}"
        nos.append({"id": no, "tipo": "PUBLIC_CONTRACT", "numero": c.numero, "vigencia_fim": c.vigencia_fim})
        arestas += [{"de": processo, "para": no, "tipo": "RESULTED_IN"}, {"de": org, "para": no, "tipo": "SIGNED"}]
    return {"nos": nos, "arestas": arestas}
