"""Compliance Matrix (§34): TR × Portfolio × Certificações × Atestados ×
Equipe × Parceiros. Determinística e explicável (C0).

| Situação | Status |
|---|---|
| Requisito ainda só sugerido pela IA | REQUIRES_REVIEW |
| Documento do cofre casa e vale até o prazo da proposta | COMPLIANT |
| Documento casa mas vence antes do prazo | NON_COMPLIANT (risco: renovar) |
| Documento casa mas sem data de validade | REQUIRES_REVIEW |
| Requisito documental sem documento, mas a oferta declara atender | PARTIALLY_COMPLIANT |
| Requisito técnico/comercial que a Offer Intelligence declara atender | COMPLIANT (autodeclarado) |
| Nada casa | UNKNOWN (nunca "não atende" por falta de dado) |
| Humano ajustou | status manual + justificativa (prevalece) |

Cada linha: requisito, status, evidência (interna e do edital), risco, fonte.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.contexts.bids import cofre
from app.contexts.bids.tipos import CATEGORIAS_DOCUMENTAIS, CATEGORIAS_MATRIZ
from app.contexts.shared.texto import termos_em_comum
from app.models.documento_cofre import DocumentoCofre
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.requisito_licitacao import RequisitoLicitacao

FONTE = "bids.compliance_matrix.v1"
_CAMPOS_OFERTA = ("requisitos", "casos_uso", "problemas_resolvidos", "cases")


def _texto_cofre(d: DocumentoCofre) -> str:
    return " ".join(filter(None, [d.nome, d.tipo.replace("_", " "), d.emissor, d.escopo, *(d.palavras_chave or [])]))


def _evidencia_edital(req: RequisitoLicitacao, documentos: dict[int, DocumentoLicitacao]) -> dict:
    doc = documentos.get(req.documento_id)
    return {
        "documento_id": req.documento_id,
        "documento": doc.nome_arquivo if doc else None,
        "sha256": doc.sha256 if doc else None,
        "fonte": doc.fonte if doc else "MANUAL",
        "fonte_url": doc.fonte_url if doc else None,
        "pagina": req.pagina,
        "clausula": req.clausula,
        "trecho": req.evidencia,
    }


def _linha(req, status, motivo, evidencia_interna, risco, fonte_interna, documentos) -> dict:
    return {
        "requisito_id": req.id,
        "categoria": req.categoria,
        "requisito": req.descricao,
        "status": status,
        "status_calculado": status,
        "motivo": motivo,
        "evidencia": evidencia_interna,
        "evidencia_edital": _evidencia_edital(req, documentos),
        "risco": risco,
        "fonte": fonte_interna,
        "ajuste_manual": None,
    }


def calcular(db: Session, tenant_id: str, licitacao: Licitacao) -> dict:
    requisitos = (
        db.query(RequisitoLicitacao)
        .filter(
            RequisitoLicitacao.tenant_id == tenant_id,
            RequisitoLicitacao.licitacao_id == licitacao.id,
            RequisitoLicitacao.status != "descartado",
            RequisitoLicitacao.categoria.in_(CATEGORIAS_MATRIZ),
        )
        .order_by(RequisitoLicitacao.id)
        .all()
    )
    documentos = {
        d.id: d for d in db.query(DocumentoLicitacao).filter_by(tenant_id=tenant_id, licitacao_id=licitacao.id).all()
    }
    cofre_docs = cofre.listar(db, tenant_id)
    ofertas = (
        [db.get(Oferta, licitacao.oferta_id)] if licitacao.oferta_id
        else db.query(Oferta).filter_by(tenant_id=tenant_id, disponivel_para_venda=True).all()
    )
    ofertas = [o for o in ofertas if o is not None and o.tenant_id == tenant_id]
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    data_limite = (licitacao.prazo_proposta.date() if licitacao.prazo_proposta else date.today())

    linhas = []
    for req in requisitos:
        doc_casado = next((d for d in cofre_docs if termos_em_comum(req.descricao, _texto_cofre(d))), None)
        oferta_casada = next(
            ((o, campo, item) for o in ofertas for campo in _CAMPOS_OFERTA for item in (getattr(o, campo) or [])
             if item and termos_em_comum(req.descricao, item)),
            None,
        )
        certificacao_perfil = next(
            (c for c in ((perfil.certificacoes if perfil else None) or []) if termos_em_comum(req.descricao, c)), None
        )

        if req.status == "sugerido":
            linha = _linha(req, "REQUIRES_REVIEW", "Requisito extraído pela IA e ainda não confirmado.", [], None, None, documentos)
        elif doc_casado is not None:
            evid = [{"tipo": "cofre", "id": doc_casado.id, "nome": doc_casado.nome, "valido_ate": doc_casado.valido_ate,
                     "sha256": doc_casado.sha256}]
            valido = cofre.valido_em(doc_casado, data_limite)
            if valido is True:
                linha = _linha(req, "COMPLIANT", f"Documento \"{doc_casado.nome}\" válido até {doc_casado.valido_ate:%d/%m/%Y}.",
                               evid, None, "cofre", documentos)
            elif valido is False:
                linha = _linha(req, "NON_COMPLIANT", f"\"{doc_casado.nome}\" não estará válido no prazo da proposta.",
                               evid, "Renovar o documento antes do prazo.", "cofre", documentos)
            else:
                linha = _linha(req, "REQUIRES_REVIEW", f"\"{doc_casado.nome}\" casa, mas sem validade informada no cofre.",
                               evid, "Conferir validade.", "cofre", documentos)
        elif oferta_casada is not None:
            oferta, campo, item = oferta_casada
            evid = [{"tipo": "oferta", "id": oferta.id, "nome": oferta.nome, "campo": campo, "trecho": item}]
            if req.categoria in CATEGORIAS_DOCUMENTAIS:
                linha = _linha(req, "PARTIALLY_COMPLIANT", "Capacidade declarada na oferta, sem documento comprobatório no cofre.",
                               evid, "Anexar comprovação (atestado/certificação) ao cofre.", "offer_intelligence", documentos)
            else:
                linha = _linha(req, "COMPLIANT", f"A oferta \"{oferta.nome}\" declara: \"{item}\".", evid,
                               None, "offer_intelligence", documentos)
        elif certificacao_perfil is not None:
            linha = _linha(req, "PARTIALLY_COMPLIANT", f"Perfil da empresa declara \"{certificacao_perfil}\", sem documento no cofre.",
                           [{"tipo": "perfil", "trecho": certificacao_perfil}], "Anexar o certificado ao cofre.", "perfil", documentos)
        else:
            linha = _linha(req, "UNKNOWN", "Nenhum documento, oferta ou certificação cadastrada casa com este requisito.",
                           [], "Verificar manualmente." if req.categoria in CATEGORIAS_DOCUMENTAIS else None, None, documentos)

        if req.conformidade_manual:
            linha["status"] = req.conformidade_manual
            linha["ajuste_manual"] = {"justificativa": req.justificativa_manual, "por_usuario_id": req.revisado_por_usuario_id,
                                      "em": req.revisado_em}
        linhas.append(linha)

    contagem = {s: 0 for s in ("COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "UNKNOWN", "REQUIRES_REVIEW")}
    for linha in linhas:
        contagem[linha["status"]] += 1
    return {"licitacao_id": licitacao.id, "fonte": FONTE, "linhas": linhas, "contagem": contagem, "total": len(linhas)}
