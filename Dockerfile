FROM python:3.12-slim

WORKDIR /app

# Dependências de sistema mínimas (compilação de pacotes Python nativos,
# ex. bcrypt) — psycopg[binary] já traz wheel pronta, não precisa disso.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN pip install --no-cache-dir .

# Pasta de materiais enviados no onboarding (E1-H2) — precisa existir e ser gravável
RUN mkdir -p /app/storage/materiais

EXPOSE 8000

# $PORT é injetado pelo Render (Onda G); localmente cai no default 8000.
# `alembic upgrade head` roda o schema de produção (Postgres) antes do
# Uvicorn subir — em dev/SQLite é idempotente, não faz nada de novo se
# já estiver em dia.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
