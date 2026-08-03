from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
_connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}

engine = create_engine(_database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
