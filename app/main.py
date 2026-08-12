import logging

import sentry_sdk
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
    LimiteDeTaxaExcedido,
    NaoAutenticado,
    NaoAutorizado,
    NaoEncontrado,
    RegraNegocioViolada,
    ValidacaoFalhou,
)

configure_logging()

logger = logging.getLogger(__name__)

settings.validar_segredos_de_producao()

# Observabilidade (raio-X de produção) — sem DSN configurada, é um no-op
# completo (nada de rede, nada de overhead), então isto é seguro de deixar
# sempre presente no código em vez de só quando alguém lembrar de ligar.
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="production" if settings.e_ambiente_producao else "development",
        traces_sample_rate=0.1,
    )

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
    allow_origins=settings.origens_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    """FastAPI não adiciona nenhum destes por padrão — sem eles, o
    navegador do usuário fica sem proteção de browser contra clickjacking,
    MIME-sniffing e downgrade pra HTTP."""
    resposta = await call_next(request)
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.e_ambiente_producao:
        resposta.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resposta


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


@app.exception_handler(LimiteDeTaxaExcedido)
async def handle_limite_de_taxa_excedido(request: Request, exc: LimiteDeTaxaExcedido) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detalhe": str(exc)})


@app.exception_handler(Exception)
async def handle_erro_inesperado(request: Request, exc: Exception) -> JSONResponse:
    """Rede de segurança contra bugs não mapeados nas classes de erro
    acima (ex.: uma dependência externa como o Neo4j fora do ar) — sem
    isto, o FastAPI devolve `{"detail": "Internal Server Error"}` (chave
    em inglês, sem acento), que o frontend não reconhece e mostra uma
    mensagem genérica sem explicar nada pro usuário. Loga o erro de
    verdade (Sentry, se configurado) e devolve um `detalhe` honesto, sem
    vazar stack trace pro cliente."""
    logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
    if settings.sentry_dsn:
        sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detalhe": "Ocorreu um erro inesperado. Tente novamente em instantes."},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
