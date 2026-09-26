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
Motor: Evaluation Engine compartilhado (`sourcing.avaliacao`, direção PROPRIA);
aqui ficam só as regras do lado vendedor.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.contexts.bids import cofre
from app.contexts.bids.tipos import CATEGORIAS_DOCUMENTAIS, CATEGORIAS_MATRIZ
from app.contexts.shared.texto import termos_em_comum
from app.contexts.sourcing import contract as sourcing
from app.models.documento_cofre import DocumentoCofre
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.oferta import Oferta
from app.models.perfil_empresa import PerfilEmpresa
from app.models.requisito_licitacao import RequisitoLicitacao

FONTE = "bids.compliance_matrix.v1"
Decisao = sourcing.avaliacao.Decisao
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


def _linha(req, decisao: sourcing.avaliacao.Decisao, documentos) -> dict:
    return {
        "requisito_id": req.id,
        "categoria": req.categoria,
        "requisito": req.descricao,
        "obrigatorio": req.obrigatorio,
        "status": decisao.status,
        "status_calculado": decisao.status,
        "motivo": decisao.motivo,
        "evidencia": decisao.evidencia,
        "evidencia_edital": _evidencia_edital(req, documentos),
        "risco": decisao.risco,
        "fonte": decisao.fonte,
        "ajuste_manual": None,
    }


def _regras(cofre_docs, ofertas, perfil, data_limite) -> list[sourcing.avaliacao.Regra]:
    """Direção PROPRIA ("atendemos?"): cofre → oferta → perfil, nessa ordem."""

    def pelo_cofre(req):
        doc = next((d for d in cofre_docs if termos_em_comum(req.descricao, _texto_cofre(d))), None)
        if doc is None:
            return None
        evid = [{"tipo": "cofre", "id": doc.id, "nome": doc.nome, "valido_ate": doc.valido_ate, "sha256": doc.sha256}]
        valido = cofre.valido_em(doc, data_limite)
        if valido is True:
            return Decisao("COMPLIANT", f"Documento \"{doc.nome}\" válido até {doc.valido_ate:%d/%m/%Y}.", evid, None, "cofre")
        if valido is False:
            return Decisao("NON_COMPLIANT", f"\"{doc.nome}\" não estará válido no prazo da proposta.", evid,
                           "Renovar o documento antes do prazo.", "cofre")
        return Decisao("REQUIRES_REVIEW", f"\"{doc.nome}\" casa, mas sem validade informada no cofre.", evid,
                       "Conferir validade.", "cofre")

    def pela_oferta(req):
        casada = next(
            ((o, campo, item) for o in ofertas for campo in _CAMPOS_OFERTA for item in (getattr(o, campo) or [])
             if item and termos_em_comum(req.descricao, item)),
            None,
        )
        if casada is None:
            return None
        oferta, campo, item = casada
        evid = [{"tipo": "oferta", "id": oferta.id, "nome": oferta.nome, "campo": campo, "trecho": item}]
        if req.categoria in CATEGORIAS_DOCUMENTAIS:
            return Decisao("PARTIALLY_COMPLIANT", "Capacidade declarada na oferta, sem documento comprobatório no cofre.",
                           evid, "Anexar comprovação (atestado/certificação) ao cofre.", "offer_intelligence")
        return Decisao("COMPLIANT", f"A oferta \"{oferta.nome}\" declara: \"{item}\".", evid, None, "offer_intelligence")

    def pelo_perfil(req):
        certificacao = next(
            (c for c in ((perfil.certificacoes if perfil else None) or []) if termos_em_comum(req.descricao, c)), None)
        if certificacao is None:
            return None
        return Decisao("PARTIALLY_COMPLIANT", f"Perfil da empresa declara \"{certificacao}\", sem documento no cofre.",
                       [{"tipo": "perfil", "trecho": certificacao}], "Anexar o certificado ao cofre.", "perfil")

    return [pelo_cofre, pela_oferta, pelo_perfil]


def _sem_decisao(req) -> Decisao:
    return Decisao("UNKNOWN", "Nenhum documento, oferta ou certificação cadastrada casa com este requisito.", [],
                   "Verificar manualmente." if req.categoria in CATEGORIAS_DOCUMENTAIS else None, None)


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
    ofertas = (
        [db.get(Oferta, licitacao.oferta_id)] if licitacao.oferta_id
        else db.query(Oferta).filter_by(tenant_id=tenant_id, disponivel_para_venda=True).all()
    )
    ofertas = [o for o in ofertas if o is not None and o.tenant_id == tenant_id]
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    data_limite = (licitacao.prazo_proposta.date() if licitacao.prazo_proposta else date.today())
    regras = _regras(cofre.listar(db, tenant_id), ofertas, perfil, data_limite)

    linhas = []
    for req in requisitos:
        decisao = sourcing.avaliacao.decidir(req, regras, req.status == "sugerido", _sem_decisao)
        linhas.append(sourcing.avaliacao.ajustar(
            _linha(req, decisao, documentos), req.conformidade_manual,
            {"justificativa": req.justificativa_manual, "por_usuario_id": req.revisado_por_usuario_id, "em": req.revisado_em},
        ))
    return {"licitacao_id": licitacao.id, "fonte": FONTE, "direcao": sourcing.avaliacao.Direcao.PROPRIA.value, "linhas": linhas,
            "contagem": sourcing.avaliacao.contar(linhas), "total": len(linhas)}
