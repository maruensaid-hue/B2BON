"""MAP Intelligence comercial (D-080): alertas acionáveis por regras determinísticas e a visão Daily Comercial.

Sinais determinísticos (cobertura, conversão, estagnação, mix, risco de quota) são regras com limiares da política —
reproduzíveis e auditáveis. IA não é usada aqui: não agregaria interpretação a um número que a regra já explica.
"""

from app.contexts.map.performance.tipos import Severidade

ORDEM_SEVERIDADE = {Severidade.CRITICA.value: 0, Severidade.ALTA.value: 1, Severidade.MEDIA.value: 2, Severidade.INFO.value: 3}


def _alerta(codigo: str, severidade: Severidade, mensagem: str, acao: str, evidencias: list | None = None) -> dict:
    return {"codigo": codigo, "severidade": severidade.value, "mensagem": mensagem, "acao": acao, "evidencias": evidencias or []}


def _top(negocios: list[dict], n: int) -> list[dict]:
    return [{"id": x["id"], "nome": x["nome"], "conta": x["conta"], "valor": x["valor"], "dias_sem_acao": x["dias_sem_acao"]}
            for x in sorted(negocios, key=lambda x: -x["valor"])[:n]]


def alertas(painel: dict, pipeline: list[dict], politica: dict) -> list[dict]:
    regras, n = politica["alertas"], politica["alertas"]["max_negocios_daily"]
    resultado = []
    quota, gap = painel["quota"], painel["gap"]
    semana = (painel["atividade"] or {}).get("semana") or {}
    atividade_pct = (semana.get("contas_trabalhadas") or {}).get("pct")
    ticket, baseline = painel["ticket_medio"], painel["ticket_medio_baseline"]
    if atividade_pct is not None and atividade_pct >= regras["atividade_alta_pct"] and ticket is not None and ticket < baseline * regras["ticket_baixo_pct"]:
        resultado.append(_alerta("HIGH_ACTIVITY_LOW_TICKET", Severidade.MEDIA,
                                 f"Atividade em {atividade_pct:.0%} da meta, mas ticket médio R$ {ticket:,.2f} (baseline R$ {baseline:,.2f}).",
                                 "Priorizar contas com fit para Suite, Bid Intelligence ou Strategic Sourcing."))
    cobertura, multiplo = painel["pipeline"]["cobertura"], painel["pipeline"]["multiplo_alvo"]
    if quota and cobertura is not None and cobertura < multiplo:
        resultado.append(_alerta("PIPELINE_COVERAGE_LOW", Severidade.ALTA,
                                 f"Cobertura de pipeline {cobertura:.1f}x a quota (alvo {multiplo:.1f}x; alvo gerencial R$ {painel['pipeline']['alvo']:,.2f}).",
                                 "Gerar oportunidades qualificadas: contas trabalhadas → reuniões."))
    sem_atividade = [x for x in pipeline if x["proposta_sem_atividade"]]
    if sem_atividade:
        resultado.append(_alerta("PROPOSAL_WITHOUT_ACTIVITY", Severidade.ALTA, f"{len(sem_atividade)} proposta(s) sem ação recente.",
                                 "Fazer follow-up das propostas abertas hoje.", _top(sem_atividade, n)))
    estagnadas = [x for x in pipeline if x["estagnada"] and not x["proposta_sem_atividade"]]
    if estagnadas:
        resultado.append(_alerta("STALLED_OPPORTUNITIES", Severidade.MEDIA, f"{len(estagnadas)} oportunidade(s) estagnada(s).",
                                 "Definir próximo passo com data ou encerrar como perdida.", _top(estagnadas, n)))
    taxas, base = painel["taxas_mes"] or {}, painel["funil_baseline"]
    baixas = [etapa for etapa, taxa in taxas.items() if taxa is not None and taxa < base[etapa] * regras["conversao_baixa_pct"]]
    if baixas:
        resultado.append(_alerta("LOW_CONVERSION", Severidade.MEDIA, f"Conversão abaixo de {regras['conversao_baixa_pct']:.0%} do baseline em: "
                                 + ", ".join(baixas) + ".", "Revisar abordagem/qualificação na etapa com o gestor."))
    if painel["mix"]["mix_quality"] == "LOW_TICKET_MIX":
        resultado.append(_alerta("LOW_TICKET_MIX", Severidade.INFO,
                                 f"Só {painel['mix']['alto_valor_participacao']:.0%} do New MRR em Suite/Bid Intelligence/Strategic Sourcing.",
                                 "Indicador, sem bloqueio: mantenha a oferta adequada ao cliente e busque contas de maior valor."))
    if quota and painel["forecast_new_mrr"] < quota * regras["risco_quota_pct"]:
        resultado.append(_alerta("QUOTA_AT_RISK", Severidade.CRITICA,
                                 f"Forecast R$ {painel['forecast_new_mrr']:,.2f} para quota R$ {quota:,.2f} (gap R$ {gap:,.2f}).",
                                 "Plano de recuperação: negócios que fecham no mês + aceleração de propostas."))
    fecham = [x for x in pipeline if x["fecha_no_periodo"]]
    if gap and sum(x["valor_ponderado"] for x in fecham) >= gap:
        resultado.append(_alerta("GAP_COVERABLE", Severidade.INFO, "Oportunidades que fecham no mês são suficientes para cobrir o gap.",
                                 "Concentrar a semana nestes negócios.", _top(fecham, n)))
    return sorted(resultado, key=lambda a: ORDEM_SEVERIDADE[a["severidade"]])


def daily(paineis: list[dict], politica: dict) -> list[dict]:
    """Daily Comercial de 15 minutos: só quem precisa de intervenção, o gap, os negócios que destravam a quota e a próxima
    ação. Nunca carrega o pipeline inteiro: no máximo `max_negocios_daily` negócios por representante."""
    n = politica["alertas"]["max_negocios_daily"]
    linhas = []
    for painel in paineis:
        criticos = [a for a in painel["alertas"] if a["severidade"] in (Severidade.CRITICA.value, Severidade.ALTA.value)]
        if not criticos and not painel["pendencias"]:
            continue
        destravam = sorted((x for x in painel["_pipeline"] if x["fecha_no_periodo"]), key=lambda x: -x["valor_ponderado"])[:n]
        linhas.append({
            "representante": painel["representante"], "attainment": painel["attainment"], "gap": painel["gap"],
            "forecast_new_mrr": painel["forecast_new_mrr"], "cobertura": painel["pipeline"]["cobertura"],
            "alertas": criticos, "pendencias": painel["pendencias"],
            "negocios_que_destravam": [{"id": x["id"], "nome": x["nome"], "conta": x["conta"], "valor": x["valor"],
                                        "probabilidade": x["probabilidade"], "fechamento_previsto": x["fechamento_previsto"],
                                        "proximo_passo": x["proximo_passo"] or "Definir próximo passo com data"} for x in destravam],
            "proximas_acoes": [a["acao"] for a in criticos][:3],
        })
    return sorted(linhas, key=lambda linha: (min((ORDEM_SEVERIDADE[a["severidade"]] for a in linha["alertas"]), default=9),
                                             -(linha["gap"] or 0)))
