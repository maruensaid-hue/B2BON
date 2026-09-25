"""Contrato público do contexto B2B ON Intelligence (Fase 4)."""

from app.contexts.intelligence import aprendizado, brain, context_engine, perfis, prompt_seguro, registro, roteador
from app.contexts.intelligence.gateway import ContextoIA, estimar, execucao, gerar
from app.contexts.shared.ferramentas import ContextoFerramenta, FerramentaExecutavel, Parametro, registrar

__all__ = ["ContextoFerramenta", "ContextoIA", "FerramentaExecutavel", "Parametro", "registrar", "aprendizado", "brain", "context_engine", "estimar", "execucao", "gerar", "perfis", "prompt_seguro", "registro", "roteador"]

from app.contexts.intelligence import ferramentas as _ferramentas  # noqa: E402, F401
from app.contexts.intelligence import orquestrador  # noqa: E402
