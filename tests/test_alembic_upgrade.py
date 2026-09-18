"""Fase 7B, hardening — rede de segurança que faltava: nenhum teste
validava `alembic upgrade head` de verdade (a suíte cria schema via
`Base.metadata.create_all()`, que nunca roda SQL de migração). Um erro
de SQL específico de dialeto (ex.: `sa.text('now()')` em vez de
`sa.func.now()` — bug real cometido e corrigido manualmente na Fase 6A
desta sessão) só aparecia rodando `alembic upgrade head` à mão contra
SQLite/Postgres, nunca no CI. Este teste roda a migração de verdade
contra um SQLite temporário isolado (engine próprio, não o `engine`
global da aplicação) a cada execução da suíte."""

import os
import tempfile

from alembic import command
from alembic.config import Config

from app.core.config import settings


def test_alembic_upgrade_head_roda_sem_erro(monkeypatch):
    fd, caminho_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho_db)  # o próprio SQLite/alembic recria o arquivo

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho_db}")
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
    finally:
        if os.path.exists(caminho_db):
            os.remove(caminho_db)
