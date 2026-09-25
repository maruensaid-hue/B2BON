"""Contrato público do contexto B2B ON Intelligence (Fase 4)."""

from app.contexts.intelligence import aprendizado, brain, context_engine, perfis, prompt_seguro, registro, roteador
from app.contexts.intelligence.gateway import ContextoIA, gerar

__all__ = ["ContextoIA", "aprendizado", "brain", "context_engine", "gerar", "perfis", "prompt_seguro", "registro", "roteador"]
