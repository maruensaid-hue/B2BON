"""Campanhas comerciais com acelerador (D-080) — ex.: Summer Sales Challenge (Dez/26 + Jan/27).

O bônus incide sobre a comissão das NOVAS vendas da janela (clientes cuja 1ª mensalidade foi paga dentro dela),
nunca sobre a carteira histórica. Faixa pelo attainment de New MRR na janela; bônus só com elegibilidade:
venda em cada mês, CRM atualizado, carteira adimplente e sem bloqueio por política comercial. Tudo vem da versão
ativa da campanha (configurável e auditada).
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.map.performance import configuracao, receita
from app.contexts.map.performance.tipos import PREFIXO_CAMPANHA, SituacaoCarteira
from app.models.representante import Representante


def _meses(inicio: date, fim: date) -> list[str]:
    meses, cursor = [], inicio.replace(day=1)
    while cursor <= fim:
        meses.append(cursor.strftime("%Y-%m"))
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return meses


def faixa(attainment: float, faixas: list[dict]) -> dict:
    escolhida = faixas[0]
    for item in faixas:
        if attainment >= item["de"]:
            escolhida = item
    return escolhida


def avaliar(regras: dict, representantes: list[Representante], hoje: date, novos: list[dict], situacoes: list[dict],
            pipeline: dict[int, list[dict]], comissoes: list[dict]) -> dict:
    inicio, fim = date.fromisoformat(regras["inicio"]), date.fromisoformat(regras["fim"])
    fim_comissao = fim + timedelta(days=regras.get("dias_comissao_apos_fim", 0))
    meses, elegibilidade = _meses(inicio, fim), regras["elegibilidade"]
    situacao = "NOT_STARTED" if hoje < inicio else ("RUNNING" if hoje <= fim else "FINISHED")
    por_rep = {}
    for rep in representantes:
        clientes = [c for c in novos if c["representante_id"] == rep.id]
        novos_tenants = {c["tenant_id"] for c in clientes}
        mrr = round(sum(c["valor"] for c in clientes), 2)
        attainment = round(mrr / regras["meta_individual"], 4)
        escolhida = faixa(attainment, regras["faixas"])
        # Base: só a comissão de clientes NOVOS da janela, sobre mensalidades recebidas na janela (+ extensão).
        base_linhas = [c for c in comissoes if c["representante_id"] == rep.id and c["tenant_id"] in novos_tenants
                       and inicio <= c["recebido_em"] <= fim_comissao and c["status"] not in ("REVERSED", "FAILED")]
        base = round(sum(c["valor"] for c in base_linhas if c["status"] != "AWAITING_COST_PARAMETERS"), 2)
        vendas_por_mes = {m: sum(1 for c in clientes if c["primeiro_pagamento_em"].strftime("%Y-%m") == m) for m in meses}
        abertos = pipeline.get(rep.id, [])
        crm_pct = round(sum(1 for n in abertos if n["atualizada"]) / len(abertos), 4) if abertos else 1.0
        inadimplentes = [s["cliente"] for s in situacoes if s["representante_id"] == rep.id and s["situacao"] == SituacaoCarteira.INADIMPLENTE.value]
        motivos = []
        if elegibilidade.get("venda_em_cada_mes") and any(v == 0 for m, v in vendas_por_mes.items() if m <= hoje.strftime("%Y-%m")):
            motivos.append("Sem venda nova em algum mês da campanha")
        if crm_pct < elegibilidade.get("crm_atualizado_pct", 0):
            motivos.append(f"CRM desatualizado ({crm_pct:.0%} das oportunidades atualizadas)")
        if elegibilidade.get("carteira_adimplente") and inadimplentes:
            motivos.append(f"Carteira com inadimplência ({len(inadimplentes)} cliente(s))")
        bloqueio = (elegibilidade.get("bloqueados") or {}).get(str(rep.id))
        if bloqueio:
            motivos.append(f"Política comercial: {bloqueio}")
        elegivel = not motivos
        por_rep[rep.id] = {
            "situacao": situacao, "meta": regras["meta_individual"], "new_mrr": mrr, "attainment": attainment, "faixa_bonus": escolhida["bonus"],
            "vendas_por_mes": vendas_por_mes, "base_comissao_novas_vendas": base,
            "comissoes_aguardando_parametros": sum(1 for c in base_linhas if c["status"] == "AWAITING_COST_PARAMETERS"),
            "elegivel": elegivel, "motivos_inelegibilidade": motivos,
            "bonus": round(base * escolhida["bonus"], 2) if elegivel else 0.0,
            "status_bonus": "FINAL" if situacao == "FINISHED" else "PROJECTED",
        }
    mrr_equipe = round(sum(r["new_mrr"] for r in por_rep.values()), 2)
    meta_equipe = regras.get("meta_equipe") or regras["meta_individual"] * len(representantes)
    return {"situacao": situacao, "inicio": inicio, "fim": fim, "por_representante": por_rep,
            "equipe": {"meta": meta_equipe, "new_mrr": mrr_equipe, "attainment": round(mrr_equipe / meta_equipe, 4) if meta_equipe else None,
                       "bonus_total": round(sum(r["bonus"] for r in por_rep.values()), 2)}}


def avaliar_todas(db: Session, representantes: list[Representante], hoje: date, situacoes: list[dict], pipeline: dict[int, list[dict]],
                  comissoes: list[dict], politica: dict) -> list[dict]:
    """Campanhas ativas cuja janela já começou ou começa nos próximos 60 dias (uma consulta de New MRR por campanha)."""
    resultado = []
    for item in configuracao.campanhas(db):
        regras = item.regras
        inicio, fim = date.fromisoformat(regras["inicio"]), date.fromisoformat(regras["fim"])
        if hoje < inicio - timedelta(days=60):
            continue
        novos = receita.novos_clientes(db, [r.id for r in representantes], datetime.combine(inicio, datetime.min.time()),
                                       datetime.combine(fim + timedelta(days=1), datetime.min.time()), politica)
        avaliacao = avaliar(regras, representantes, hoje, novos, situacoes, pipeline, comissoes)
        resultado.append({"codigo": item.codigo.removeprefix(PREFIXO_CAMPANHA), "nome": regras["nome"], "versao": item.versao,
                          "faixas": regras["faixas"], **avaliacao})
    return resultado
