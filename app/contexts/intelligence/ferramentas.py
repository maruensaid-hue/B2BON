"""Ferramentas transversais do B2B ON Intelligence Agent (Fase 12)."""

from app.contexts.intelligence import context_engine
from app.contexts.shared.ferramentas import FerramentaExecutavel, Parametro, registrar


def _buscar_brain(db, ctx, parametros: dict) -> dict:
    contexto = context_engine.montar(db, ctx.tenant_id, context_engine.Proposito.USO_INTERNO, parametros["consulta"])
    return {"resumo": f"{len(contexto.fontes)} item(ns) do Corporate Brain encontrados." if contexto.fontes
            else "Nada no Corporate Brain sobre isso.", "fontes": contexto.fontes}


registrar(FerramentaExecutavel(
    "brain.buscar", agente="sales_strategy_agent", lado="NEUTRO",
    palavras_chave=("cérebro corporativo", "brain", "conhecimento da empresa", "o que sabemos sobre"),
    parametros=(Parametro("consulta"),), executar=_buscar_brain, exemplo="O que o Corporate Brain sabe sobre nossa política de preços?",
))
registrar(FerramentaExecutavel(
    "predator.rascunho_mensagem", agente="cadence_agent", lado="SELL",
    palavras_chave=("escrever mensagem", "rascunho de mensagem", "mandar mensagem", "enviar email"),
))
registrar(FerramentaExecutavel(
    "plataforma.alterar_plano", agente="b2bon_intelligence_agent", lado="NEUTRO",
    palavras_chave=("alterar plano", "mudar plano", "trocar plano", "upgrade de plano", "cancelar assinatura"),
))
