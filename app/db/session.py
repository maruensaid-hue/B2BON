from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def normalizar_database_url(database_url: str) -> str:
    """Normaliza o esquema da URL para o driver psycopg3 — Neon/Render
    devolvem `postgres://` ou `postgresql://`, que o SQLAlchemy 2.x
    resolveria para o psycopg2 (não instalado) se não for explícito
    (Onda G)."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


_database_url = normalizar_database_url(settings.database_url)
_eh_sqlite = _database_url.startswith("sqlite")
# `timeout` (segundos que o SQLite espera por um lock antes de desistir,
# padrão 5s) e `NullPool` (sem teto artificial de conexões simultâneas)
# evitam "QueuePool limit... connection timed out" quando o backend web
# e um script em lote (ex.: carregar_recorte_receita_federal) acessam o
# mesmo arquivo .db ao mesmo tempo — SQLite só aceita um escritor por
# vez, e sem isso a segunda conexão desiste rápido demais em vez de
# esperar a primeira liberar o lock (Onda H).
_connect_args = {"check_same_thread": False, "timeout": 30} if _eh_sqlite else {}

engine = create_engine(_database_url, connect_args=_connect_args, poolclass=NullPool if _eh_sqlite else None)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
