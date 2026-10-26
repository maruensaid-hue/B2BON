"""Ajustes de sessão aplicados pelo `alembic/env.py` ao rodar as migrações."""

import os
import re

_PADRAO_DURACAO = re.compile(r"^\d+(ms|s|min)$")
LIMITE_DE_ESPERA_PADRAO = "30s"


def comando_limite_de_espera(dialeto: str) -> str | None:
    """Limite de espera por bloqueio das migrações no PostgreSQL.

    Sem ele, um `ALTER TABLE` fica esperando indefinidamente enquanto outro processo (por exemplo, um envio longo da versão anterior) mantém a
    tabela em uso: a subida do serviço pendura até o prazo do Render e o deploy falha sem dizer por quê. Com o limite, a migração falha em segundos
    com "canceling statement due to lock timeout", o deploy não vai ao ar e a versão anterior segue atendendo. `SET LOCAL` vale só para a
    transação da migração, então funciona também atrás de pgbouncer. Ajustável por `ALEMBIC_LOCK_TIMEOUT` (ex.: `90s`, `500ms`)."""
    if dialeto != "postgresql":
        return None
    valor = os.environ.get("ALEMBIC_LOCK_TIMEOUT", LIMITE_DE_ESPERA_PADRAO).strip()
    if not _PADRAO_DURACAO.match(valor):
        raise ValueError(f"ALEMBIC_LOCK_TIMEOUT inválido: {valor!r} (use, por exemplo, 30s, 500ms ou 2min)")
    return f"SET LOCAL lock_timeout = '{valor}'"
