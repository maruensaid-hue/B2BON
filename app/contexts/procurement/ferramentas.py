"""Ferramentas do lado comprador para o Intelligence Agent (Fase 12).

Registradas daqui (barreira Buy/Sell): o orquestrador não importa este
contexto; só executa estas ferramentas para quem tem o módulo procurement,
sempre no tenant do próprio usuário.
"""

from app.contexts.shared.ferramentas import FerramentaExecutavel, Parametro, registrar
from app.contexts.procurement import contratos, estrategico, estrategico_sinais, riscos
from app.models.contrato_compra import ContratoCompra

DIAS = 120


def _contratos(db, ctx, parametros: dict) -> dict:
    itens = []
    vigentes = db.query(ContratoCompra).filter_by(tenant_id=ctx.tenant_id, status="VIGENTE").all()
    intel_contratos = contratos.inteligencia_em_lote(db, ctx.tenant_id, vigentes)
    for c in vigentes:
        intel = intel_contratos[c.id]
        if intel["dias_para_fim"] is not None and intel["dias_para_fim"] <= DIAS:
            itens.append({"contrato_id": c.id, "objeto": c.objeto, "vigencia_fim": c.vigencia_fim, "dias_para_fim": intel["dias_para_fim"],
                          "necessidade_continuada": c.necessidade_continuada, "saldo": intel["saldo"]})
    alertas = [s for s in riscos.sinais(db, ctx.tenant_id)["sinais"] if s["tipo"] == "CONTRACT_EXPIRING"]
    itens.sort(key=lambda i: i["dias_para_fim"])
    return {"resumo": f"{len(itens)} contrato(s) com fornecedores vencendo em até {DIAS} dias; {len(alertas)} sem processo sucessor.",
            "itens": itens, "sinais": alertas, "aviso": riscos.AVISO}


def _pca(db, ctx, parametros: dict) -> dict:
    sinais = [s for s in riscos.sinais(db, ctx.tenant_id)["sinais"] if s["tipo"] in ("INCOMPLETE_PLANNING", "PROCESS_DELAY")]
    return {"resumo": f"{len(sinais)} item(ns) do PCA ou processo(s) pedindo revisão de prazo.", "sinais": sinais, "aviso": riscos.AVISO}


registrar(FerramentaExecutavel(
    "procurement.contratos_vencendo", agente="contract_intelligence_agent", lado="BUY",
    palavras_chave=("contratos próximos do vencimento", "contratos vencendo", "contratos a vencer", "renovação de contrato"),
    executar=_contratos, exemplo="Mostre contratos com fornecedores próximos do vencimento.",
))
registrar(FerramentaExecutavel(
    "procurement.pca_atrasado", agente="procurement_planning_agent", lado="BUY",
    palavras_chave=("compras do pca atrasadas", "pca atrasado", "plano de contratações atrasado", "processos atrasados"),
    executar=_pca, exemplo="Quais compras do PCA estão atrasadas?",
))


# --- Phase G: Strategic Sourcing (módulo sourcing), determinísticas ------------------------------
def _comparar(db, ctx, parametros: dict) -> dict:
    processo_id = parametros.get("processo_id")
    if processo_id is None:  # sem número: o processo em decisão mais recente
        processo_id = next((p.id for p in estrategico.listar(db, ctx.tenant_id)
                            if p.status in ("EM_AVALIACAO", "EM_NEGOCIACAO", "EM_APROVACAO")), None)
        if processo_id is None:
            return {"resumo": "Nenhum processo de sourcing em avaliação. Informe o número do processo."}
    comparacao = estrategico.comparar(db, ctx.tenant_id, int(processo_id))
    nomes = {linha["participante_id"]: linha["participante"] for linha in comparacao["linhas"]}
    destaques = comparacao["destaques"]
    partes = [f"{len(comparacao['linhas'])} proposta(s) no processo {comparacao['processo_id']}"]
    if destaques["menor_valor"]:
        partes.append(f"menor valor entre as que atendem os obrigatórios: {nomes[destaques['menor_valor']]}")
    if destaques["maior_nota"]:
        partes.append(f"maior nota técnica: {nomes[destaques['maior_nota']]}")
    return {"resumo": "; ".join(partes) + ". A escolha é sua.", **comparacao}


def _historico(db, ctx, parametros: dict) -> dict:
    achados = estrategico_sinais.historico_por_nome(db, ctx.tenant_id, parametros.get("pergunta") or "")
    if not achados:
        return {"resumo": "Não encontrei esse fornecedor nos seus processos de sourcing. Cite o nome como está cadastrado.", "fornecedores": []}
    return {"resumo": "; ".join(f"{a['fornecedor']}: {a['processos']} processo(s), respondeu {a['respondeu']}, venceu {a['adjudicado']}"
                                for a in achados), "fornecedores": achados}


def _pendencias(db, ctx, parametros: dict) -> dict:
    itens = estrategico_sinais.pendencias(db, ctx.tenant_id)
    com_alerta = sum(1 for i in itens if i["alertas"])
    return {"resumo": f"{len(itens)} processo(s) de sourcing em aberto; {com_alerta} com alerta.", "processos": itens}


registrar(FerramentaExecutavel(
    "sourcing.comparar_propostas", agente="procurement_intelligence_agent", lado="BUY",
    palavras_chave=("compare as propostas", "comparar propostas", "comparação das propostas", "melhor proposta recebida"),
    parametros=(Parametro("processo_id", r"processo\s*#?\s*(\d+)", obrigatorio=False),), executar=_comparar,
    exemplo="Compare as três propostas do processo 12.",
))
registrar(FerramentaExecutavel(
    "sourcing.historico_fornecedor", agente="procurement_intelligence_agent", lado="BUY",
    palavras_chave=("histórico do fornecedor", "desempenho do fornecedor", "como foi o fornecedor"),
    parametros=(Parametro("pergunta"),), executar=_historico, exemplo="Qual o histórico do fornecedor Móveis Delta?",
))
registrar(FerramentaExecutavel(
    "sourcing.pendencias", agente="procurement_intelligence_agent", lado="BUY",
    palavras_chave=("processos de sourcing", "pendências de sourcing", "riscos do sourcing", "cotações em aberto"),
    executar=_pendencias, exemplo="Quais processos de sourcing precisam de atenção?",
))
