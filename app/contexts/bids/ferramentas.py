"""Ferramentas do Bid Intelligence (lado vendedor) para o Intelligence Agent (Fase 12)."""

from app.contexts.bids import conformidade, contratos, go_no_go, licitacoes, prazos
from app.contexts.shared.ferramentas import FerramentaExecutavel, Parametro, registrar


def _analisar(db, ctx, parametros: dict) -> dict:
    lic = licitacoes.obter(db, ctx.tenant_id, parametros["licitacao_id"])
    matriz = conformidade.calcular(db, ctx.tenant_id, lic)
    rec = go_no_go.recomendar(db, ctx.tenant_id, lic, matriz)
    return {"resumo": f"Recomendação {rec['recomendacao']}: {rec['motivo']} Matriz: {matriz['contagem']}.",
            "recomendacao": rec, "matriz": matriz["contagem"], "prazos": prazos.listar(db, ctx.tenant_id, licitacao_id=lic.id),
            "aviso": "A decisão Go/No-Go é humana."}


def _prazos(db, ctx, parametros: dict) -> dict:
    itens = prazos.proximos(db, ctx.tenant_id)
    return {"resumo": f"{len(itens)} prazo(s) nos próximos 30 dias ou vencidos.", "itens": itens}


def _contratos(db, ctx, parametros: dict) -> dict:
    itens = contratos.sinais(db, ctx.tenant_id)
    return {"resumo": f"{len(itens)} contrato(s) ganho(s) pedindo ação (renovação ou nova licitação).", "itens": itens}


registrar(FerramentaExecutavel(
    "bids.analisar_licitacao", agente="bid_qualification_agent", lado="SELL",
    palavras_chave=("analise este edital", "analisar edital", "analise a licitação", "go no go", "vale a pena participar"),
    parametros=(Parametro("licitacao_id", r"(?:licita[cç][aã]o|edital|preg[aã]o)\s*#?\s*(\d+)"),), executar=_analisar,
    exemplo="Analise o edital 5.",
))
registrar(FerramentaExecutavel(
    "bids.prazos", agente="bid_qualification_agent", lado="SELL",
    palavras_chave=("prazos das licitações", "prazo de proposta", "licitações vencendo", "entregas de proposta"),
    executar=_prazos, exemplo="Quais prazos de licitação estão vencendo?",
))
registrar(FerramentaExecutavel(
    "bids.contratos_vencendo", agente="contract_intelligence_agent", lado="SELL",
    palavras_chave=("contratos próximos do vencimento", "contratos vencendo", "contratos a vencer", "renovação de contrato"),
    executar=_contratos, exemplo="Mostre contratos com clientes próximos do vencimento.",
))
