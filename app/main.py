from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401 — registra as tabelas em Base.metadata
from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine
from app.services.errors import (
    NaoAutenticado,
    NaoAutorizado,
    NaoEncontrado,
    RegraNegocioViolada,
    ValidacaoFalhou,
)

configure_logging()

# Dev/testes (SQLite): cria as tabelas que ainda não existem a cada
# start, idempotente. Produção (Postgres, Onda G): o schema é
# gerenciado inteiramente pelo Alembic (`alembic upgrade head`, rodado
# pelo CMD do Dockerfile antes do Uvicorn subir) — rodar create_all
# aqui também faria o Postgres ganhar as tabelas sem o registro de
# versão do Alembic, quebrando migrações futuras.
if settings.database_url.startswith("sqlite"):
    Base.metadata.create_all(bind=engine)

app = FastAPI(title="B2B ON — PREDATOR", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.exception_handler(NaoEncontrado)
async def handle_nao_encontrado(request: Request, exc: NaoEncontrado) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detalhe": str(exc)})


@app.exception_handler(RegraNegocioViolada)
async def handle_regra_negocio_violada(request: Request, exc: RegraNegocioViolada) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detalhe": str(exc)})


@app.exception_handler(ValidacaoFalhou)
async def handle_validacao_falhou(request: Request, exc: ValidacaoFalhou) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detalhe": str(exc)})


@app.exception_handler(NaoAutenticado)
async def handle_nao_autenticado(request: Request, exc: NaoAutenticado) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detalhe": str(exc)})


@app.exception_handler(NaoAutorizado)
async def handle_nao_autorizado(request: Request, exc: NaoAutorizado) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detalhe": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
