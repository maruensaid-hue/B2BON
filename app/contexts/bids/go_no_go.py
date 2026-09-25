"""Go/No-Go (§35): recomendação explicável; a decisão é do humano autorizado.

Nove fatores do §35 + prazo. Cada fator: status (FAVORAVEL | ATENCAO |
DESFAVORAVEL | UNKNOWN), motivo e evidência. Fatores sem dado ficam
UNKNOWN: se metade ou mais estiver UNKNOWN, a recomendação é
INSUFFICIENT_INFORMATION. Bloqueios (prazo vencido, requisito documental
NON_COMPLIANT) recomendam NO_GO.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.contexts.bids.tipos import CATEGORIAS_DOCUMENTAIS
from app.contexts.crm.contract import valor_ganho_por_conta
from app.models.licitacao import Licitacao
from app.models.oferta import Oferta

FONTE = "bids.go_no_go.v1"
F, A, D, U = "FAVORAVEL", "ATENCAO", "DESFAVORAVEL", "UNKNOWN"


def _fator(nome: str, status: str, motivo: str, evidencia: list | None = None) -> dict:
    return {"fator": nome, "status": status, "motivo": motivo, "evidencia": evidencia or []}


def recomendar(db: Session, tenant_id: str, licitacao: Licitacao, matriz: dict, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(UTC)
    linhas = matriz["linhas"]
    fatores: list[dict] = []
    bloqueios: list[str] = []

    tecnicas = [l for l in linhas if l["categoria"] not in CATEGORIAS_DOCUMENTAIS]
    if tecnicas:
        atendidas = sum(1 for l in tecnicas if l["status"] == "COMPLIANT")
        pct = atendidas / len(tecnicas)
        status = F if pct >= 0.7 else A if pct >= 0.4 else D
        fatores.append(_fator("Technical Fit", status, f"{atendidas} de {len(tecnicas)} requisitos técnicos/comerciais atendidos.",
                              [l["requisito_id"] for l in tecnicas]))
    else:
        fatores.append(_fator("Technical Fit", U, "Nenhum requisito técnico confirmado na matriz."))

    documentais = [l for l in linhas if l["categoria"] in CATEGORIAS_DOCUMENTAIS]
    if documentais:
        nao = [l for l in documentais if l["status"] == "NON_COMPLIANT"]
        ok = sum(1 for l in documentais if l["status"] == "COMPLIANT")
        if nao:
            bloqueios.append(f"{len(nao)} requisito(s) de habilitação/qualificação não atendido(s).")
        status = D if nao else F if ok == len(documentais) else A
        fatores.append(_fator("Qualification", status, f"{ok} de {len(documentais)} requisitos de habilitação comprovados.",
                              [l["requisito_id"] for l in documentais]))
        pendentes = [l for l in documentais if l["status"] in ("UNKNOWN", "REQUIRES_REVIEW", "PARTIALLY_COMPLIANT")]
        fatores.append(_fator("Documentation", D if nao else A if pendentes else F,
                              f"{len(pendentes)} documento(s) a providenciar ou conferir.", [l["requisito_id"] for l in pendentes]))
    else:
        fatores.append(_fator("Qualification", U, "Nenhum requisito de habilitação confirmado."))
        fatores.append(_fator("Documentation", U, "Sem requisitos documentais para conferir."))

    oferta = db.get(Oferta, licitacao.oferta_id) if licitacao.oferta_id else None
    if licitacao.valor_estimado is not None and oferta is not None and oferta.ticket_medio:
        razao = licitacao.valor_estimado / oferta.ticket_medio
        fatores.append(_fator("Commercial Fit", F if razao >= 0.5 else A,
                              f"Valor estimado R$ {licitacao.valor_estimado:,.2f} vs ticket médio R$ {oferta.ticket_medio:,.2f}.",
                              [f"oferta:{oferta.id}"]))
    else:
        fatores.append(_fator("Commercial Fit", U, "Sem valor estimado na licitação ou ticket médio na oferta."))

    if oferta is not None and oferta.margem_media is not None:
        fatores.append(_fator("Margin", F if oferta.margem_media >= 20 else A,
                              f"Margem média da oferta: {oferta.margem_media:.1f}%.", [f"oferta:{oferta.id}"]))
    else:
        fatores.append(_fator("Margin", U, "Margem não cadastrada na oferta vinculada."))

    if licitacao.conta_id is not None:
        ganho = valor_ganho_por_conta(db, tenant_id, [licitacao.conta_id]).get(licitacao.conta_id, 0.0)
        fatores.append(_fator("Relationship", F if ganho else A,
                              f"R$ {ganho:,.2f} em negócios ganhos com este órgão/conta." if ganho else "Conta vinculada, sem negócio ganho.",
                              [f"conta:{licitacao.conta_id}"]))
    else:
        fatores.append(_fator("Relationship", U, "Licitação não vinculada a uma conta do CRM."))

    concorrentes = licitacao.concorrentes or []
    fatores.append(_fator("Competitive Position", A if concorrentes else U,
                          f"{len(concorrentes)} concorrente(s) conhecido(s): {', '.join(concorrentes)}." if concorrentes
                          else "Concorrentes não informados.", concorrentes))
    fatores.append(_fator("Delivery Capacity", U, "Capacidade de entrega não é medida pela plataforma: avaliar com a operação."))
    fatores.append(_fator("Strategic Fit", F if licitacao.oferta_id else U,
                          "Licitação vinculada a uma oferta do portfólio." if licitacao.oferta_id else "Sem oferta vinculada."))

    if licitacao.prazo_proposta is not None:
        dias = (licitacao.prazo_proposta.replace(tzinfo=UTC) - agora).days
        if dias < 0:
            bloqueios.append("O prazo de proposta já passou.")
        fatores.append(_fator("Deadline", D if dias < 0 else A if dias < 5 else F,
                              "Prazo vencido." if dias < 0 else f"{dias} dia(s) até a proposta."))
    else:
        fatores.append(_fator("Deadline", U, "Prazo de proposta não informado."))

    desconhecidos = sum(1 for f in fatores if f["status"] == U)
    if bloqueios:
        recomendacao, motivo = "NO_GO", " ".join(bloqueios)
    elif desconhecidos * 2 >= len(fatores):
        recomendacao, motivo = "INSUFFICIENT_INFORMATION", f"{desconhecidos} de {len(fatores)} fatores sem dado."
    elif sum(1 for f in fatores if f["status"] == D) >= 2:
        recomendacao, motivo = "NO_GO", "Dois ou mais fatores desfavoráveis."
    else:
        recomendacao, motivo = "GO", "Sem bloqueios e com a maioria dos fatores conhecidos favoráveis ou em atenção."
    return {
        "recomendacao": recomendacao,
        "motivo": motivo,
        "fatores": fatores,
        "bloqueios": bloqueios,
        "fonte": FONTE,
        "gerado_em": agora,
        "decisao_final": "Humana: a plataforma recomenda e explica, quem decide é o responsável autorizado.",
    }
