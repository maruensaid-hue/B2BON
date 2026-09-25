"""White Space (§24) e MAP + Opportunity Intelligence (§26), por conta.

Valor potencial só é estimado quando TODAS as ofertas potenciais têm
ticket médio cadastrado; senão volta `null` com o motivo.
"""

from app.contexts.opportunity import texto
from app.contexts.opportunity.dados import DadosOportunidade
from app.contexts.opportunity.explicavel import Confianca, Evidencia, FonteEvidencia, recomendacao
from app.contexts.opportunity.nbo import CATEGORIAS_CASAVEIS, itens_oferta, ofertas_por_nome, avaliar, churn_alto, evidencia_churn

FONTE = "opportunity.white_space.v1"


def analisar(dados: DadosOportunidade) -> dict:
    atuais = [o for o in dados.ofertas if o.id in dados.ofertas_compradas_ids]
    necessidades = dados.necessidades_da_conta
    potenciais = []
    for oferta in dados.ofertas:
        if oferta.id in dados.ofertas_compradas_ids:
            continue
        avaliacao = avaliar(dados, oferta, necessidades)
        if avaliacao["score"] > 0 and avaliacao["evidencias"]:
            potenciais.append((oferta, avaliacao))

    suprimir = churn_alto(dados)
    comprados = dados.ofertas_compradas_ids
    cross_sell = [] if suprimir else _unicos(x for o in atuais for x in ofertas_por_nome(dados.ofertas, o.cross_sell, comprados))
    upsell = [] if suprimir else _unicos(x for o in atuais for x in ofertas_por_nome(dados.ofertas, o.upsell, set()))

    nao_atendidas = []
    for n in necessidades:
        if n.status != "confirmada" or n.categoria not in CATEGORIAS_CASAVEIS:
            continue
        if not any(texto.termos_em_comum(n.descricao, item) for o in dados.ofertas for _, item in itens_oferta(o)):
            nao_atendidas.append({"necessidade_id": n.id, "descricao": n.descricao, "categoria": n.categoria})

    if not potenciais:
        potencial, motivo_potencial = None, "Nenhuma oferta potencial identificada."
    elif any(o.ticket_medio is None for o, _ in potenciais):
        sem = [o.nome for o, _ in potenciais if o.ticket_medio is None]
        potencial, motivo_potencial = None, f"Ticket médio não cadastrado em: {', '.join(sem)}."
    else:
        potencial, motivo_potencial = float(sum(o.ticket_medio for o, _ in potenciais)), None

    sinais = []
    if suprimir:
        sinais.append(recomendacao(
            "sinal_map", "Churn alto: não expandir agora",
            "Conta cliente com risco crítico no MAP. Cross-sell e upsell ficam suprimidos até a remediação (§26).",
            [evidencia_churn(dados)], Confianca.ALTA, FONTE, gerado_em=dados.agora,
        ))
    elif (
        dados.e_cliente
        and dados.risco_map is not None
        and dados.risco_map["classificacao"] == "saudavel"
        and dados.conta.nps_classificacao == "promotor"
        and (potenciais or cross_sell or upsell)
    ):
        sinais.append(recomendacao(
            "sinal_map", "Oportunidade de expansão",
            "Cliente saudável no MAP, promotor no NPS e com espaço em branco no portfólio.",
            [
                evidencia_churn(dados),
                Evidencia("conta", dados.conta.id, f"NPS promotor (nota {dados.conta.nps_nota})", FonteEvidencia.CADASTRO),
                Evidencia("portfolio", None, f"{len(potenciais)} oferta(s) potencial(is), {len(cross_sell)} cross-sell, {len(upsell)} upsell", FonteEvidencia.CALCULO),
            ],
            Confianca.MEDIA, FONTE, gerado_em=dados.agora,
        ))

    return {
        "conta_id": dados.conta.id,
        "produtos_atuais": [{"oferta_id": o.id, "nome": o.nome} for o in atuais],
        "produtos_potenciais": [
            {"oferta_id": o.id, "nome": o.nome, "fit_score": a["score"], "confianca": a["confianca"], "ticket_medio": o.ticket_medio}
            for o, a in sorted(potenciais, key=lambda par: -par[1]["score"])
        ],
        "cross_sell": cross_sell,
        "upsell": upsell,
        "expansao_suprimida_por_churn": suprimir,
        "necessidades_nao_atendidas": nao_atendidas,
        "potencial_estimado": potencial,
        "potencial_estimado_motivo_nulo": motivo_potencial,
        "valor_ja_ganho": dados.valor_ganho_conta,
        "sinais": sinais,
    }


def _unicos(itens) -> list[dict]:
    vistos: dict[int, dict] = {}
    for item in itens:
        vistos.setdefault(item["oferta_id"], item)
    return list(vistos.values())
