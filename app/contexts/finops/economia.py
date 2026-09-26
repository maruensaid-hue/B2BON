"""AI Credit Economics (Fase 15): receita, custo, margem e calibração.

    AI REVENUE − AI VARIABLE COST = AI GROSS PROFIT
    AI GROSS PROFIT / AI REVENUE  = AI GROSS MARGIN

- Receita = créditos consumidos × receita por crédito do lote de onde
  saíram (top-up: preço pago; franquia de assinatura: referência
  configurada em `comercial`; promocional/ajuste: zero), mais excedente
  pós-pago. Execução estornada ou liberada tem receita zero e custo real.
- Custo = custo variável medido (LLM + dados) convertido por câmbio
  configurado. Sem câmbio ou sem preço do modelo, o custo em reais fica
  desconhecido e a margem volta `None` com o motivo — nunca estimada.
- Tudo aqui é análise: nada altera preço, peso ou franquia. A
  recomendação de peso só sugere; a mudança é versão nova aprovada.
"""

import math
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.contexts.bids import contract as bids
from app.contexts.finops import carteira, catalogos, comercial
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import AlertaCreditos, CompraCreditos, ConfiguracaoCreditosTenant, ExecucaoIa, LoteCreditos
from app.models.negocio import Negocio
from app.models.plano import Plano
from app.models.qualificacao import QualificacaoScore
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.reuniao import Reuniao

ZERO = Decimal(0)
AMOSTRA_MINIMA = 20
DIMENSOES = ("tenant", "modulo", "workload", "agente", "plano", "provider", "modelo", "pacote")
_COLUNA = {"tenant": ExecucaoIa.tenant_id, "modulo": ExecucaoIa.modulo, "workload": ExecucaoIa.workload_codigo,
           "agente": ExecucaoIa.agente, "plano": ExecucaoIa.plano_id}
_MOTIVO_SEM_CAMBIO = "Configure FINOPS_CAMBIO_USD_BRL: custo é medido em USD e a receita em BRL."


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _f(valor, casas: int = 4) -> float | None:
    return None if valor is None else round(float(valor), casas)


def _margem(receita: Decimal, custo: Decimal | None) -> Decimal | None:
    if custo is None or receita <= 0:
        return None
    return ((receita - custo) / receita).quantize(Decimal("0.0001"))


def janela(dias: int, agora: datetime | None = None) -> tuple[datetime, datetime]:
    fim = agora or carteira.agora_utc()
    return fim - timedelta(days=dias), fim


def _execucoes(db: Session, inicio: datetime, fim: datetime, tenant_id: str | None = None):
    consulta = db.query(ExecucaoIa).filter(ExecucaoIa.criado_em >= inicio, ExecucaoIa.criado_em < fim,
                                          ExecucaoIa.status.in_(("LIQUIDADA", "ESTORNADA", "LIBERADA")))
    return consulta.filter(ExecucaoIa.tenant_id == tenant_id) if tenant_id else consulta


def _linha(chave, execucoes: list[ExecucaoIa]) -> dict:
    receita = sum((_d(e.receita_brl) for e in execucoes), ZERO)
    desconhecido = any(e.custo_total_brl is None for e in execucoes)
    custo = None if desconhecido else sum((_d(e.custo_total_brl) for e in execucoes), ZERO)
    creditos = sum((_d(e.creditos_liquidados) + _d(e.creditos_excedente) for e in execucoes if e.status == "LIQUIDADA"), ZERO)
    margem = _margem(receita, custo)
    return {
        "chave": chave, "execucoes": len(execucoes), "creditos": _f(creditos, 2), "receita_brl": _f(receita, 2),
        "custo_usd": _f(sum((_d(e.custo_total_usd) for e in execucoes), ZERO), 6), "custo_brl": _f(custo, 2),
        "lucro_bruto_brl": _f(receita - custo, 2) if custo is not None else None, "margem_bruta": _f(margem),
        "nivel": comercial.nivel_margem(margem), "amostra_suficiente": len(execucoes) >= AMOSTRA_MINIMA,
    }


def margens(db: Session, dimensao: str, inicio: datetime, fim: datetime, tenant_id: str | None = None) -> list[dict]:
    if dimensao not in DIMENSOES:
        raise ValueError(f"Dimensão inválida: {dimensao}")
    execucoes = _execucoes(db, inicio, fim, tenant_id).all()
    if dimensao in _COLUNA:
        grupos: dict = {}
        for execucao in execucoes:
            grupos.setdefault(getattr(execucao, _COLUNA[dimensao].key), []).append(execucao)
        linhas = [_linha(chave, lista) for chave, lista in grupos.items()]
        if dimensao == "plano":
            nomes = {p.id: p.nome for p in db.query(Plano).all()}
            for linha in linhas:
                linha["chave"] = nomes.get(linha["chave"], "Sem plano")
        return sorted(linhas, key=lambda linha: -(linha["receita_brl"] or 0))
    if dimensao in ("provider", "modelo"):
        return _por_chamada(db, dimensao, execucoes)
    return _por_pacote(db, execucoes)


def _por_chamada(db: Session, dimensao: str, execucoes: list[ExecucaoIa]) -> list[dict]:
    """Receita da execução repartida pelo custo de cada chamada (provider/modelo)."""
    por_id = {e.id: e for e in execucoes}
    coluna = RegistroUsoIa.provider if dimensao == "provider" else RegistroUsoIa.model
    grupos: dict = {}
    for chave, execucao_id, custo in db.query(coluna, RegistroUsoIa.execucao_id, RegistroUsoIa.custo_usd).filter(
            RegistroUsoIa.execucao_id.in_(list(por_id) or ["-"]), RegistroUsoIa.status == "sucesso").all():
        execucao = por_id[execucao_id]
        total = _d(execucao.custo_total_usd)
        fatia = _d(custo) / total if total > 0 else Decimal(1) / max(execucao.chamadas or 1, 1)
        item = grupos.setdefault(chave or "desconhecido", {"chamadas": 0, "custo_usd": ZERO, "receita": ZERO, "custo_brl": ZERO,
                                                           "desconhecido": False})
        item["chamadas"] += 1
        item["custo_usd"] += _d(custo)
        item["receita"] += _d(execucao.receita_brl) * fatia
        if execucao.custo_total_brl is None:
            item["desconhecido"] = True
        else:
            item["custo_brl"] += _d(execucao.custo_total_brl) * fatia
    linhas = []
    for chave, item in grupos.items():
        custo = None if item["desconhecido"] else item["custo_brl"]
        margem = _margem(item["receita"], custo)
        linhas.append({"chave": chave, "chamadas": item["chamadas"], "custo_usd": _f(item["custo_usd"], 6),
                       "receita_brl": _f(item["receita"], 2), "custo_brl": _f(custo, 2), "margem_bruta": _f(margem),
                       "nivel": comercial.nivel_margem(margem)})
    return sorted(linhas, key=lambda linha: -(linha["custo_usd"] or 0))


def _por_pacote(db: Session, execucoes: list[ExecucaoIa]) -> list[dict]:
    """Margem por origem do crédito consumido (pacote comprado, franquia, promoção)."""
    por_id = {e.id: e for e in execucoes}
    grupos: dict = {}
    consumos = db.query(MovimentoCredito, LoteCreditos).join(LoteCreditos, LoteCreditos.id == MovimentoCredito.lote_id).filter(
        MovimentoCredito.execucao_id.in_(list(por_id) or ["-"]), MovimentoCredito.tipo == "CREDIT_CONSUMED").all()
    for movimento, lote in consumos:
        execucao = por_id[movimento.execucao_id]
        chave = lote.origem.removeprefix("PACOTE:") if lote.tipo == "TOPUP" else lote.tipo
        consumido = -_d(movimento.quantidade)
        total = _d(execucao.creditos_liquidados) or Decimal(1)
        item = grupos.setdefault(chave, {"creditos": ZERO, "receita": ZERO, "custo": ZERO, "desconhecido": False})
        item["creditos"] += consumido
        item["receita"] += _d(movimento.receita_brl)
        if execucao.custo_total_brl is None:
            item["desconhecido"] = True
        else:
            item["custo"] += _d(execucao.custo_total_brl) * consumido / total
    linhas = []
    for chave, item in grupos.items():
        custo = None if item["desconhecido"] else item["custo"]
        margem = _margem(item["receita"], custo)
        linhas.append({"chave": chave, "creditos": _f(item["creditos"], 2), "receita_brl": _f(item["receita"], 2),
                       "custo_brl": _f(custo, 2), "margem_bruta": _f(margem), "nivel": comercial.nivel_margem(margem)})
    return sorted(linhas, key=lambda linha: -(linha["receita_brl"] or 0))


def _somar_movimentos(db: Session, tipos: tuple[str, ...], inicio: datetime, fim: datetime, tenant_id: str | None = None,
                      **filtros) -> Decimal:
    consulta = db.query(func.sum(MovimentoCredito.quantidade)).filter(
        MovimentoCredito.tipo.in_(tipos), MovimentoCredito.criado_em >= inicio, MovimentoCredito.criado_em < fim)
    if tenant_id:
        consulta = consulta.filter(MovimentoCredito.tenant_id == tenant_id)
    for campo, valor in filtros.items():
        consulta = consulta.filter(getattr(MovimentoCredito, campo) == valor)
    return _d(consulta.scalar())


def kpis(db: Session, inicio: datetime, fim: datetime, tenant_id: str | None = None) -> dict:
    execucoes = _execucoes(db, inicio, fim, tenant_id).all()
    geral = _linha("geral", execucoes)
    consumidos = -_somar_movimentos(db, ("CREDIT_CONSUMED", "CREDIT_REFUNDED"), inicio, fim, tenant_id)
    compras = db.query(func.sum(CompraCreditos.creditos), func.sum(CompraCreditos.preco)).filter(
        CompraCreditos.status == "APROVADA", CompraCreditos.confirmado_em >= inicio, CompraCreditos.confirmado_em < fim)
    if tenant_id:
        compras = compras.filter(CompraCreditos.tenant_id == tenant_id)
    vendidos, faturado_pacotes = compras.one()
    passivo = db.query(func.sum(LoteCreditos.quantidade_restante), func.sum(LoteCreditos.quantidade_restante * LoteCreditos.receita_por_credito_brl)).filter(
        LoteCreditos.status == "ATIVO", LoteCreditos.tipo == "TOPUP")
    if tenant_id:
        passivo = passivo.filter(LoteCreditos.tenant_id == tenant_id)
    creditos_passivo, valor_passivo = passivo.one()
    excedente = db.query(func.sum(MovimentoCredito.receita_brl), func.sum(MovimentoCredito.quantidade)).filter(
        MovimentoCredito.tipo == "CREDIT_OVERAGE", MovimentoCredito.faturavel.is_(True), MovimentoCredito.criado_em >= inicio,
        MovimentoCredito.criado_em < fim)
    if tenant_id:
        excedente = excedente.filter(MovimentoCredito.tenant_id == tenant_id)
    receita_excedente, creditos_excedente = excedente.one()
    custo_brl = geral["custo_brl"]
    receita = geral["receita_brl"] or 0
    return {
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "ai_revenue_brl": receita, "ai_variable_cost_brl": custo_brl, "ai_variable_cost_usd": geral["custo_usd"],
        "ai_gross_profit_brl": geral["lucro_bruto_brl"], "ai_gross_margin": geral["margem_bruta"], "nivel_margem": geral["nivel"],
        "margem_alvo": float(comercial.faixas_margem().alvo),
        "motivo_indisponivel": _MOTIVO_SEM_CAMBIO if comercial.cambio_usd_brl() is None else (
            "Há execuções com modelo sem preço cadastrado." if custo_brl is None and execucoes else None),
        "execucoes": len(execucoes),
        "credits_sold": int(vendidos or 0), "credits_sold_revenue_brl": _f(faturado_pacotes, 2) or 0.0,
        "credits_granted": _f(_somar_movimentos(db, ("CREDIT_GRANTED", "CREDIT_PROMOTIONAL", "CREDIT_PURCHASED"), inicio, fim, tenant_id), 2),
        "credits_consumed": _f(consumidos, 2), "credits_expired": _f(-_somar_movimentos(db, ("CREDIT_EXPIRED",), inicio, fim, tenant_id), 2),
        "unused_credit_liability": {"creditos": _f(creditos_passivo, 2) or 0.0, "valor_brl": _f(valor_passivo, 2) or 0.0},
        "overage": {"creditos": _f(-_d(creditos_excedente), 2), "receita_brl": _f(receita_excedente, 2) or 0.0},
        "avg_cost_per_1k_credits_brl": _f(Decimal(str(custo_brl)) / consumidos * 1000, 2) if custo_brl is not None and consumidos > 0 else None,
        "avg_revenue_per_1k_credits_brl": _f(Decimal(str(receita)) / consumidos * 1000, 2) if consumidos > 0 else None,
        "cache_savings_usd": _f(sum((_d(e.economia_cache_usd) for e in execucoes), ZERO), 6),
        "cache_hit_rate": _taxa_cache(db, inicio, fim, tenant_id),
        "provider_distribution": _distribuicao(db, RegistroUsoIa.provider, inicio, fim, tenant_id),
        "model_distribution": _distribuicao(db, RegistroUsoIa.model, inicio, fim, tenant_id),
    }


def _taxa_cache(db: Session, inicio, fim, tenant_id=None) -> float | None:
    consulta = db.query(func.count(RegistroUsoIa.id), func.sum(case((RegistroUsoIa.cache_hit.is_(True), 1), else_=0))).filter(
        RegistroUsoIa.criado_em >= inicio, RegistroUsoIa.criado_em < fim, RegistroUsoIa.status == "sucesso")
    if tenant_id:
        consulta = consulta.filter(RegistroUsoIa.tenant_id == tenant_id)
    total, hits = consulta.one()
    return round((hits or 0) / total, 4) if total else None


def _distribuicao(db: Session, coluna, inicio, fim, tenant_id=None) -> list[dict]:
    consulta = db.query(coluna, func.count(RegistroUsoIa.id), func.sum(RegistroUsoIa.custo_usd)).filter(
        RegistroUsoIa.criado_em >= inicio, RegistroUsoIa.criado_em < fim, RegistroUsoIa.status == "sucesso")
    if tenant_id:
        consulta = consulta.filter(RegistroUsoIa.tenant_id == tenant_id)
    linhas = consulta.group_by(coluna).all()
    total = sum(n for _, n, _ in linhas) or 1
    return sorted(({"chave": chave or "desconhecido", "chamadas": n, "participacao": round(n / total, 4), "custo_usd": _f(custo, 6)}
                   for chave, n, custo in linhas), key=lambda item: -item["chamadas"])


def alertas_margem(db: Session, agora: datetime | None = None, janelas: tuple[int, ...] = (7, 30),
                   amostra_minima: int = AMOSTRA_MINIMA) -> list[dict]:
    """MARGIN_WARNING/CRITICAL por janela e dimensão, só com amostra mínima:
    uma operação excepcional não dispara alerta estratégico."""
    resultado = []
    for dias in janelas:
        inicio, fim = janela(dias, agora)
        linhas = [("geral", _linha("geral", _execucoes(db, inicio, fim).all()))]
        linhas += [("modulo", linha) for linha in margens(db, "modulo", inicio, fim)]
        linhas += [("workload", linha) for linha in margens(db, "workload", inicio, fim)]
        for dimensao, linha in linhas:
            if linha["execucoes"] < amostra_minima or linha["nivel"] not in ("MARGIN_WARNING", "MARGIN_CRITICAL"):
                continue
            resultado.append({"alerta": linha["nivel"], "janela_dias": dias, "dimensao": dimensao, "chave": linha["chave"],
                              "margem_bruta": linha["margem_bruta"], "execucoes": linha["execucoes"],
                              "limite": float(comercial.faixas_margem().critica if linha["nivel"] == "MARGIN_CRITICAL" else comercial.faixas_margem().alerta)})
    return resultado


def matriz_rentabilidade(db: Session, inicio: datetime, fim: datetime) -> list[dict]:
    grupos: dict = {}
    for execucao in _execucoes(db, inicio, fim).all():
        grupos.setdefault((execucao.modulo, execucao.workload_codigo), []).append(execucao)
    linhas = []
    for (modulo, workload), lista in grupos.items():
        linha = _linha(workload, lista)
        linha.update({"modulo": modulo, "workload": workload,
                      "economicamente_inadequado": linha["nivel"] in ("MARGIN_WARNING", "MARGIN_CRITICAL") and linha["amostra_suficiente"]})
        linhas.append(linha)
    return sorted(linhas, key=lambda linha: (linha["modulo"], -(linha["receita_brl"] or 0)))


def recomendacoes_peso(db: Session, dias: int = 30, amostra_minima: int = AMOSTRA_MINIMA, agora: datetime | None = None) -> list[dict]:
    """Sugestão ANALÍTICA de peso por workload para atingir a margem-alvo:
    peso necessário = custo médio por execução ÷ (receita por crédito × (1 − alvo)).
    Nunca altera o catálogo: mudança = rascunho + aprovação."""
    inicio, fim = janela(dias, agora)
    alvo = comercial.faixas_margem().alvo
    atuais = {w.codigo: w for w in catalogos.workloads(db)}
    resultado = []
    grupos: dict = {}
    for execucao in _execucoes(db, inicio, fim).filter(ExecucaoIa.status == "LIQUIDADA").all():
        grupos.setdefault(execucao.workload_codigo, []).append(execucao)
    for codigo, lista in grupos.items():
        if len(lista) < amostra_minima or any(e.custo_total_brl is None for e in lista) or codigo not in atuais:
            continue
        creditos = sum((_d(e.creditos_liquidados) for e in lista), ZERO)
        receita = sum((_d(e.receita_brl) for e in lista), ZERO)
        custo = sum((_d(e.custo_total_brl) for e in lista), ZERO)
        if creditos <= 0 or receita <= 0:
            continue
        margem = _margem(receita, custo)
        receita_por_credito = receita / creditos
        custo_medio = custo / len(lista)
        necessario = custo_medio / (receita_por_credito * (1 - alvo))
        peso_atual = _d(atuais[codigo].creditos_base)
        minimo, maximo = math.ceil(necessario), math.ceil(necessario * Decimal("1.15"))
        direcao = "AUMENTAR" if margem is not None and margem < alvo else ("REDUZIR_POSSIVEL" if necessario * Decimal("1.5") < peso_atual else "MANTER")
        resultado.append({
            "workload": codigo, "execucoes": len(lista), "margem_bruta": _f(margem), "peso_atual": float(peso_atual),
            "peso_sugerido_min": minimo, "peso_sugerido_max": max(maximo, minimo), "direcao": direcao,
            "mensagem": (f"{atuais[codigo].nome} teve margem média de {float(margem) * 100:.0f}% nos últimos {dias} dias. "
                         f"Peso atual: {float(peso_atual):g}. Faixa sugerida: {minimo}–{max(maximo, minimo)}.") if margem is not None else None,
            "requer_aprovacao": True,
        })
    return sorted(resultado, key=lambda item: item["margem_bruta"] if item["margem_bruta"] is not None else 9)


def _custo_por(custo: Decimal | None, quantidade, motivo_zero: str) -> dict:
    if custo is None:
        return {"valor": None, "motivo": _MOTIVO_SEM_CAMBIO}
    if not quantidade:
        return {"valor": None, "motivo": motivo_zero}
    return {"valor": _f(custo / Decimal(str(quantidade)), 4), "base": _f(quantidade, 2)}


def economia_unitaria(db: Session, inicio: datetime, fim: datetime, tenant_id: str | None = None) -> dict:
    """AI Cost por unidade de negócio, quando há dados. Public Procurement
    fica no painel do próprio comprador (barreira Buy/Sell)."""
    execucoes = _execucoes(db, inicio, fim, tenant_id).all()
    custo = None if any(e.custo_total_brl is None for e in execucoes) else sum((_d(e.custo_total_brl) for e in execucoes), ZERO)

    def custo_workloads(prefixos: tuple[str, ...]):
        selecionadas = [e for e in execucoes if e.workload_codigo.startswith(prefixos)]
        if any(e.custo_total_brl is None for e in selecionadas):
            return None, len(selecionadas)
        return sum((_d(e.custo_total_brl) for e in selecionadas), ZERO), len(selecionadas)

    def contar(modelo, *filtros):
        consulta = db.query(func.count(modelo.id)).filter(modelo.criado_em >= inicio, modelo.criado_em < fim, *filtros)
        return consulta.filter(modelo.tenant_id == tenant_id).scalar() if tenant_id else consulta.scalar()

    usuarios = len({(e.tenant_id, e.usuario_id) for e in execucoes if e.usuario_id is not None})
    tenants = len({e.tenant_id for e in execucoes})
    creditos = sum((_d(e.creditos_liquidados) for e in execucoes), ZERO)
    pipeline = db.query(func.sum(Negocio.valor)).filter(Negocio.criado_em >= inicio, Negocio.criado_em < fim)
    ganho = db.query(func.sum(Negocio.valor)).filter(Negocio.ganho_em >= inicio, Negocio.ganho_em < fim)
    if tenant_id:
        pipeline, ganho = pipeline.filter(Negocio.tenant_id == tenant_id), ganho.filter(Negocio.tenant_id == tenant_id)
    custo_tender, n_tender = custo_workloads(("tender", "compliance", "full_go_no_go", "simple_rfp"))
    custo_churn, n_churn = custo_workloads(("churn_prediction",))
    custo_remediacao, n_remediacao = custo_workloads(("churn_remediation",))
    return {
        "ai_cost_per_active_user": _custo_por(custo, usuarios, "Sem usuários com uso de IA no período."),
        "ai_cost_per_tenant": _custo_por(custo, tenants, "Sem tenants com uso de IA no período."),
        "ai_cost_per_1k_credits": _custo_por(custo * 1000 if custo is not None else None, creditos, "Sem créditos consumidos."),
        "ai_cost_per_opportunity": _custo_por(custo, contar(Negocio), "Sem negócios criados no período."),
        "ai_cost_per_meeting": _custo_por(custo, contar(Reuniao), "Sem reuniões no período."),
        "ai_cost_per_qualified_lead": _custo_por(custo, contar(QualificacaoScore, QualificacaoScore.score_total >= QualificacaoScore.limiar_configurado),
                                                 "Sem leads qualificados no período."),
        "ai_cost_per_cadence": _custo_por(*custo_workloads(("cadence_generation", "prospecting_message")),
                                          "Sem geração de cadência/mensagem no período."),
        "ai_cost_per_bid": _custo_por(custo_tender, bids.repositorio.VENDA.contar_processos(db, inicio, fim, tenant_id),
                                      "Sem licitações no período."),
        "ai_cost_per_tender_analysis": _custo_por(custo_tender, n_tender, "Sem análise de edital no período."),
        "ai_cost_per_procurement_process": {"valor": None, "motivo": "Exibido no painel de Compras públicas (barreira Buy/Sell)."},
        "ai_cost_per_churn_prediction": _custo_por(custo_churn, n_churn, "Sem previsão de churn por IA no período."),
        "ai_cost_per_churn_remediation": _custo_por(custo_remediacao, n_remediacao, "Sem remediação de churn no período."),
        "ai_cost_per_brl_pipeline_generated": _custo_por(custo, pipeline.scalar(), "Sem pipeline gerado no período."),
        "ai_cost_per_brl_revenue_influenced": _custo_por(custo, ganho.scalar(), "Sem receita ganha no período."),
    }


def valor_de_negocio(db: Session, tenant_id: str, inicio: datetime, fim: datetime) -> dict:
    """Uso de IA relacionado a resultados (correlação registrada, não causalidade)."""
    execucoes = _execucoes(db, inicio, fim, tenant_id).filter(ExecucaoIa.status == "LIQUIDADA").all()

    def creditos(modulos: tuple[str, ...]) -> float:
        return _f(sum((_d(e.creditos_liquidados) for e in execucoes if e.modulo in modulos), ZERO), 2)

    negocios = db.query(Negocio).filter(Negocio.tenant_id == tenant_id, Negocio.criado_em >= inicio, Negocio.criado_em < fim).all()
    ganhos = db.query(Negocio).filter(Negocio.tenant_id == tenant_id, Negocio.ganho_em >= inicio, Negocio.ganho_em < fim).all()
    decisoes = bids.repositorio.VENDA.decisoes_go_no_go(db, tenant_id, inicio, fim)
    licitacoes = bids.repositorio.VENDA.processos_criados(db, tenant_id, inicio, fim)
    return {
        "aviso": "Relaciona consumo de IA a resultados registrados no mesmo período; não prova causalidade.",
        "prospeccao": {
            "creditos": creditos(("predator", "crm")),
            "reunioes": db.query(func.count(Reuniao.id)).filter(Reuniao.tenant_id == tenant_id, Reuniao.criado_em >= inicio,
                                                                 Reuniao.criado_em < fim).scalar(),
            "oportunidades": len(negocios), "pipeline_brl": _f(sum((_d(n.valor) for n in negocios), ZERO), 2),
            "receita_brl": _f(sum((_d(n.valor) for n in ganhos), ZERO), 2),
        },
        "churn": {"creditos": creditos(("map",)), "remediacoes": sum(1 for e in execucoes if e.workload_codigo == "churn_remediation")},
        "licitacoes": {
            "creditos": creditos(("bids",)), "qualificadas_go": sum(1 for d in decisoes if d.decisao == "GO"),
            "propostas_enviadas": sum(1 for lic in licitacoes if lic.status in ("PROPOSTA_ENVIADA", "GANHA", "PERDIDA")),
            "ganhas": sum(1 for lic in licitacoes if lic.status == "GANHA"),
            "receita_brl": _f(sum((_d(lic.valor_proposta) for lic in licitacoes if lic.status == "GANHA"), ZERO), 2),
        },
    }


def relatorio_calibracao(db: Session, dias: int, agora: datetime | None = None) -> dict:
    """AI CREDIT ECONOMICS REPORT (7/30/90 dias) — tudo recomendação."""
    inicio, fim = janela(dias, agora)
    execucoes = _execucoes(db, inicio, fim).all()
    liquidadas = [e for e in execucoes if e.status == "LIQUIDADA"]
    por_tenant: dict = {}
    for execucao in liquidadas:
        por_tenant[execucao.tenant_id] = por_tenant.get(execucao.tenant_id, ZERO) + _d(execucao.creditos_liquidados)
    usuarios = {(e.tenant_id, e.usuario_id) for e in liquidadas if e.usuario_id is not None}
    total_creditos = sum(por_tenant.values(), ZERO)
    periodos = {inicio.strftime("%Y-%m"), fim.strftime("%Y-%m")}
    alertas = db.query(AlertaCreditos).filter(AlertaCreditos.periodo.in_(periodos)).all()
    em_80 = {a.tenant_id for a in alertas if a.nivel >= 80}
    em_100 = {a.tenant_id for a in alertas if a.nivel >= 100}
    compraram = {c.tenant_id for c in db.query(CompraCreditos).filter(CompraCreditos.status == "APROVADA",
                                                                    CompraCreditos.confirmado_em >= inicio).all()}
    configs = db.query(ConfiguracaoCreditosTenant).all()
    workloads = margens(db, "workload", inicio, fim)
    return {
        "titulo": "AI CREDIT ECONOMICS REPORT", "dias": dias,
        "credit_economics": kpis(db, inicio, fim),
        "margem": {d: margens(db, d, inicio, fim) for d in ("modulo", "provider", "modelo", "pacote", "plano")},
        "usage_distribution": {
            "top_20_workloads": sorted(workloads, key=lambda w: -(w["creditos"] or 0))[:20],
            "average_credits_per_tenant": _f(total_creditos / len(por_tenant), 2) if por_tenant else None,
            "average_credits_per_active_user": _f(total_creditos / len(usuarios), 2) if usuarios else None,
        },
        "workload_profitability": matriz_rentabilidade(db, inicio, fim),
        "tenant_cohorts": {
            "tenants_com_uso": len(por_tenant), "tenants_hitting_80": len(em_80), "tenants_hitting_100": len(em_100),
            "top_up_conversion": round(len(em_80 & compraram) / len(em_80), 4) if em_80 else None,
            "auto_recharge_adoption": sum(1 for c in configs if c.recarga_ativa), "overage_enabled": sum(1 for c in configs if c.excedente_ativo),
        },
        "alertas_margem": alertas_margem(db, agora, janelas=(dias,)),
        "recommendations": recomendacoes_peso(db, dias, agora=agora),
        "aviso": "Recomendações não alteram preços, pesos nem franquias: toda mudança exige aprovação administrativa.",
    }
