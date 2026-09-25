"""Ferramentas do Opportunity Intelligence para o B2B ON Intelligence Agent (Fase 12)."""

from app.contexts.crm.contract import valor_ganho_por_conta
from app.contexts.shared.ferramentas import FerramentaExecutavel, Parametro, registrar
from app.contexts.opportunity.card import montar, white_space_da_conta


def _analisar(db, ctx, parametros: dict) -> dict:
    card = montar(db, ctx.tenant_id, parametros["negocio_id"])
    acoes = [a["titulo"] for a in card["next_best_action"]["recomendacoes"][:3]]
    ofertas = card["next_best_offer"]["recomendacoes"]
    oferta = f"Oferta mais aderente: {ofertas[0]['titulo']} (fit {ofertas[0]['dados']['fit_score']})." if ofertas else "Sem oferta recomendável ainda."
    faltando = card["discovery_gaps"]["faltando"]
    resumo = (f"Próximas ações: {'; '.join(acoes) or 'nenhuma'}. {oferta} "
              + (f"Falta descobrir: {', '.join(faltando)}." if faltando else "Discovery completo."))
    return {"resumo": resumo, "negocio_id": card["negocio_id"], "proximas_acoes": card["next_best_action"]["recomendacoes"][:3],
            "next_best_offer": ofertas[:1], "discovery": {"status": card["discovery_gaps"]["status"], "faltando": faltando}}


def _expansao(db, ctx, parametros: dict) -> dict:
    clientes = [cid for cid, valor in valor_ganho_por_conta(db, ctx.tenant_id).items() if valor > 0][:50]
    itens = []
    for conta_id in clientes:
        ws = white_space_da_conta(db, ctx.tenant_id, conta_id)
        if ws["expansao_suprimida_por_churn"]:
            continue
        if ws["produtos_potenciais"] or ws["cross_sell"] or ws["upsell"]:
            itens.append({"conta_id": conta_id, "potenciais": [p["nome"] for p in ws["produtos_potenciais"]],
                          "cross_sell": [c["nome"] for c in ws["cross_sell"]], "upsell": [u["nome"] for u in ws["upsell"]],
                          "sinal_expansao": any(s["titulo"] == "Oportunidade de expansão" for s in ws["sinais"]),
                          "potencial_estimado": ws["potencial_estimado"]})
    itens.sort(key=lambda i: (not i["sinal_expansao"], -len(i["potenciais"])))
    return {"resumo": f"{len(itens)} cliente(s) com espaço para expansão (clientes com churn crítico ficam de fora).", "itens": itens}


registrar(FerramentaExecutavel(
    "opportunity.analisar_oportunidade", agente="opportunity_agent", lado="SELL",
    palavras_chave=("analise esta oportunidade", "analisar oportunidade", "o que fazer neste negócio", "próxima ação do negócio",
                    "analise o negócio"),
    parametros=(Parametro("negocio_id", r"(?:neg[oó]cio|oportunidade)\s*#?\s*(\d+)"),), executar=_analisar,
    exemplo="Analise a oportunidade 12 e diga o que fazer.",
))
registrar(FerramentaExecutavel(
    "opportunity.clientes_expansao", agente="revenue_agent", lado="SELL",
    palavras_chave=("oportunidade de expansão", "clientes para expandir", "cross-sell", "upsell", "expansão"),
    executar=_expansao, exemplo="Quais clientes possuem oportunidade de expansão?",
))
