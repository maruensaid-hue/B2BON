"""Deadline Engine (Fase 9): o que vence e quando, num lugar só.

Fontes: prazo de proposta e de esclarecimento das licitações em aberto,
prazos extraídos dos documentos (categoria PRAZO, só como referência com a
evidência), documentos do cofre que vencem antes do prazo de uma proposta
e fim de vigência de contratos ganhos (renovação). Nível: VENCIDO,
CRITICO (≤2 dias), ATENCAO (≤7 dias; ≤90 para contratos), OK.
"""

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.contexts.bids import cofre
from app.contexts.bids.tipos import STATUS_FINAIS
from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.licitacao import Licitacao
from app.models.requisito_licitacao import RequisitoLicitacao

DIAS_CRITICO = 2
DIAS_ATENCAO = 7
DIAS_ATENCAO_CONTRATO = 90


def _nivel(dias: int, atencao: int = DIAS_ATENCAO) -> str:
    if dias < 0:
        return "VENCIDO"
    if dias <= DIAS_CRITICO:
        return "CRITICO"
    if dias <= atencao:
        return "ATENCAO"
    return "OK"


def _dias(alvo: datetime | date, hoje: date) -> int:
    alvo_data = alvo.date() if isinstance(alvo, datetime) else alvo
    return (alvo_data - hoje).days


def listar(db: Session, tenant_id: str, agora: datetime | None = None, licitacao_id: int | None = None) -> list[dict]:
    hoje = (agora or datetime.now(UTC)).date()
    itens: list[dict] = []
    consulta = db.query(Licitacao).filter(Licitacao.tenant_id == tenant_id, Licitacao.status.notin_(STATUS_FINAIS))
    if licitacao_id is not None:
        consulta = consulta.filter(Licitacao.id == licitacao_id)
    licitacoes = consulta.all()
    documentos_cofre = cofre.listar(db, tenant_id)

    for lic in licitacoes:
        for campo, rotulo in (("prazo_proposta", "Entrega da proposta"), ("prazo_esclarecimento", "Pedido de esclarecimento")):
            quando = getattr(lic, campo)
            if quando is not None:
                dias = _dias(quando, hoje)
                itens.append({"tipo": campo.upper(), "titulo": f"{rotulo}: {lic.titulo}", "quando": quando, "dias": dias,
                              "nivel": _nivel(dias), "licitacao_id": lic.id, "fonte": "licitacao"})
        if lic.prazo_proposta is not None:
            for d in documentos_cofre:
                if cofre.valido_em(d, lic.prazo_proposta.date()) is False and d.valido_ate is not None:
                    dias = _dias(d.valido_ate, hoje)
                    itens.append({"tipo": "DOCUMENTO_VENCE_ANTES_DA_PROPOSTA",
                                  "titulo": f"\"{d.nome}\" vence antes da proposta de {lic.titulo}", "quando": d.valido_ate,
                                  "dias": dias, "nivel": "CRITICO" if dias >= 0 else "VENCIDO", "licitacao_id": lic.id,
                                  "documento_cofre_id": d.id, "fonte": "cofre"})
        for req in db.query(RequisitoLicitacao).filter(
            RequisitoLicitacao.licitacao_id == lic.id, RequisitoLicitacao.categoria == "PRAZO",
            RequisitoLicitacao.status != "descartado",
        ).all():
            itens.append({"tipo": "PRAZO_DO_EDITAL", "titulo": req.descricao, "quando": None, "dias": None,
                          "nivel": "REFERENCIA", "licitacao_id": lic.id, "requisito_id": req.id,
                          "evidencia": {"documento_id": req.documento_id, "pagina": req.pagina, "trecho": req.evidencia},
                          "fonte": "documento"})

    if licitacao_id is None:
        for d in documentos_cofre:
            if cofre.status(d, hoje) in ("VENCENDO", "VENCIDO"):
                dias = _dias(d.valido_ate, hoje)
                itens.append({"tipo": "VALIDADE_DOCUMENTO", "titulo": f"Validade: {d.nome}", "quando": d.valido_ate,
                              "dias": dias, "nivel": _nivel(dias, cofre.DIAS_ALERTA), "documento_cofre_id": d.id, "fonte": "cofre"})
        for c in db.query(ContratoVendaPublica).filter_by(tenant_id=tenant_id, status="VIGENTE").all():
            if c.vigencia_fim is not None:
                dias = _dias(c.vigencia_fim, hoje)
                itens.append({"tipo": "FIM_DE_CONTRATO", "titulo": f"Fim do contrato {c.numero or c.id}: {c.objeto}",
                              "quando": c.vigencia_fim, "dias": dias, "nivel": _nivel(dias, DIAS_ATENCAO_CONTRATO),
                              "contrato_id": c.id, "fonte": "contrato"})

    ordem = {"VENCIDO": 0, "CRITICO": 1, "ATENCAO": 2, "OK": 3, "REFERENCIA": 4}
    itens.sort(key=lambda i: (ordem[i["nivel"]], i["dias"] if i["dias"] is not None else 10**6))
    return itens


def proximos(db: Session, tenant_id: str, agora: datetime | None = None, dias: int = 30) -> list[dict]:
    return [i for i in listar(db, tenant_id, agora) if i["dias"] is not None and i["dias"] <= dias]
