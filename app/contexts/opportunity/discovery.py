"""Discovery Gap (§23): o que ainda não sabemos para vender.

Cinco dimensões (necessidade, autoridade, orçamento, prazo, concorrência).
Cada uma é CONFIRMADA (dado confirmado por humano), SUGERIDA (só sugestão
da IA ou heurística de cargo) ou FALTANDO. Se alguma não está confirmada,
o resultado é INSUFFICIENT_INFORMATION com a lista do que falta e as
perguntas de descoberta (da oferta, quando cadastradas).
"""

from dataclasses import asdict

from app.contexts.opportunity.dados import DadosOportunidade
from app.contexts.opportunity.explicavel import (
    INSUFFICIENT_INFORMATION,
    Confianca,
    Evidencia,
    FonteEvidencia,
    recomendacao,
)
from app.services.conta_service import sugerir_papel_comite_compra

FONTE = "opportunity.discovery_gap.v1"
PAPEIS_AUTORIDADE = frozenset({"DECISION_MAKER", "ECONOMIC_BUYER"})

DIMENSOES: dict[str, dict] = {
    "necessidade": {
        "rotulo": "Necessidade / dor do cliente",
        "categorias": {"dor", "requisito"},
        "pergunta": "Qual problema o cliente precisa resolver e qual o impacto de não resolver?",
    },
    "autoridade": {
        "rotulo": "Quem decide / aprova a compra",
        "categorias": {"autoridade"},
        "pergunta": "Quem aprova esta compra e quem mais participa da decisão?",
    },
    "orcamento": {
        "rotulo": "Orçamento",
        "categorias": {"orcamento"},
        "pergunta": "Existe orçamento aprovado ou previsto para isto? Em que faixa?",
    },
    "prazo": {
        "rotulo": "Prazo / urgência",
        "categorias": {"prazo"},
        "pergunta": "Até quando isto precisa estar resolvido e o que define esse prazo?",
    },
    "concorrencia": {
        "rotulo": "Concorrência / alternativas",
        "categorias": {"concorrencia"},
        "pergunta": "Que outras alternativas estão sendo avaliadas (inclusive não fazer nada)?",
    },
}


def _evid_necessidade(n) -> Evidencia:
    fonte = FonteEvidencia.CONFIRMADO_POR_HUMANO if n.status == "confirmada" else FonteEvidencia.SUGESTAO_IA
    return Evidencia("necessidade", n.id, n.citacao or n.descricao, fonte)


def analisar(dados: DadosOportunidade, perguntas_da_oferta: list[str] | None = None) -> dict:
    dimensoes: dict[str, dict] = {}
    for chave, definicao in DIMENSOES.items():
        relevantes = [n for n in dados.necessidades if n.categoria in definicao["categorias"]]
        confirmadas = [n for n in relevantes if n.status == "confirmada"]
        evidencias = [_evid_necessidade(n) for n in (confirmadas or relevantes)]

        if chave == "autoridade":
            for d in dados.decisores:
                if d.papel_confirmado in PAPEIS_AUTORIDADE:
                    confirmadas.append(d)
                    evidencias.append(
                        Evidencia("decisor", d.id, f"{d.nome} ({d.cargo or 'sem cargo'}) confirmado como {d.papel_confirmado}",
                                  FonteEvidencia.CONFIRMADO_POR_HUMANO)
                    )
                elif not d.papel_confirmado and sugerir_papel_comite_compra(d.cargo) in PAPEIS_AUTORIDADE:
                    relevantes.append(d)
                    evidencias.append(
                        Evidencia("decisor", d.id, f"{d.nome} ({d.cargo}) — papel sugerido pelo cargo, não confirmado",
                                  FonteEvidencia.SUGESTAO_IA)
                    )
        if chave == "concorrencia":
            for i in dados.interacoes:
                if i.tipo == "mencionou_concorrente":
                    confirmadas.append(i)
                    evidencias.append(
                        Evidencia("interacao", i.id, i.descricao or "Cliente mencionou concorrente",
                                  FonteEvidencia.CONFIRMADO_POR_HUMANO)
                    )

        status = "CONFIRMADO" if confirmadas else ("SUGERIDO" if relevantes else "FALTANDO")
        dimensoes[chave] = {"rotulo": definicao["rotulo"], "status": status, "evidencias": evidencias}

    faltando = [c for c, d in dimensoes.items() if d["status"] != "CONFIRMADO"]
    perguntas = [DIMENSOES[c]["pergunta"] for c in faltando]
    for p in perguntas_da_oferta or []:
        if p not in perguntas:
            perguntas.append(p)

    lacunas = [
        recomendacao(
            "discovery_gap",
            f"Descobrir: {DIMENSOES[c]['rotulo']}",
            (
                "Só há sugestão não confirmada para esta dimensão; confirme com o cliente."
                if dimensoes[c]["status"] == "SUGERIDO"
                else "Nenhuma informação registrada para esta dimensão."
            ),
            dimensoes[c]["evidencias"]
            or [Evidencia("lacuna", c, f"Sem necessidade confirmada de categoria {', '.join(sorted(DIMENSOES[c]['categorias']))}"
                          + (" nem decisor com papel de decisão confirmado" if c == "autoridade" else ""),
                          FonteEvidencia.AUSENCIA)],
            Confianca.ALTA,
            FONTE,
            gerado_em=dados.agora,
            dados={"dimensao": c, "status": dimensoes[c]["status"], "pergunta": DIMENSOES[c]["pergunta"]},
        )
        for c in faltando
    ]
    return {
        "status": INSUFFICIENT_INFORMATION if faltando else "SUFICIENTE",
        "faltando": [DIMENSOES[c]["rotulo"] for c in faltando],
        "dimensoes": {
            c: {"rotulo": d["rotulo"], "status": d["status"], "evidencias": [asdict(e) for e in d["evidencias"]]}
            for c, d in dimensoes.items()
        },
        "perguntas_sugeridas": perguntas,
        "lacunas": lacunas,
    }
