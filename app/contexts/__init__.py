"""Bounded contexts do monólito modular (Fase 1 do Master Prompt v4).

Regra de fronteira (verificada por `tests/unit/test_fronteiras_contexto.py`):
código de fora de um contexto só importa o `contract.py` dele; `shared/`
é o Shared Kernel, importável por todos. Os serviços em `app/services/`
continuam existindo e migram para cá aos poucos (Strangler Pattern).
"""
