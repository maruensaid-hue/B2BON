from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.core.logging import configure_logging
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

configure_logging()

app = FastAPI(title="B2B ON — PREDATOR", version="0.1.0")

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
