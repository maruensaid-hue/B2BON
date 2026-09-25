"""Ferramentas do lado comprador para o Intelligence Agent (Fase 12).

Registradas daqui (barreira Buy/Sell): o orquestrador não importa este
contexto; só executa estas ferramentas para quem tem o módulo procurement,
sempre no tenant do próprio usuário.
"""

from app.contexts.shared.ferramentas import FerramentaExecutavel, registrar
from app.contexts.procurement import contratos, riscos
from app.models.contrato_compra import ContratoCompra

DIAS = 120


def _contratos(db, ctx, parametros: dict) -> dict:
    itens = []
    for c in db.query(ContratoCompra).filter_by(tenant_id=ctx.tenant_id, status="VIGENTE").all():
        intel = contratos.inteligencia(db, ctx.tenant_id, c)
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
