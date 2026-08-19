from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import conta_service


def test_erro_nao_tratado_devolve_detalhe_em_vez_de_estourar(client, monkeypatch):
    """Raio-X de produção: um bug não mapeado (ex.: Neo4j fora do ar)
    virava um 500 cru do FastAPI (`{"detail": "Internal Server Error"}`,
    chave em inglês) que o frontend não reconhecia — o usuário via
    "não foi possível executar essa operação" sem nenhuma explicação.
    O handler global cobre esse caso: sempre devolve `detalhe` em
    português, que é a chave que o `ApiError` do frontend lê.

    Usa um TestClient próprio com `raise_server_exceptions=False`: o
    Starlette relança a exceção original após montar a resposta do
    handler de `Exception` (de propósito, pra aparecer no console) — sem
    isso o pytest veria o `RuntimeError` simulado em vez do 500 tratado."""

    def _explode(*args, **kwargs):
        raise RuntimeError("Falha simulada")

    monkeypatch.setattr(conta_service, "criar_lead", _explode)

    with TestClient(app, raise_server_exceptions=False) as cliente_tolerante:
        cliente_tolerante.headers.update(client.headers)
        resposta = cliente_tolerante.post("/api/v1/leads/contas", json={"nome": "Empresa Teste"})

    assert resposta.status_code == 500
    assert "detalhe" in resposta.json()
    assert resposta.json()["detalhe"]


def test_erro_nao_tratado_ainda_leva_cabecalhos_de_cors(client, monkeypatch):
    """Raio-X de produção real: `ServerErrorMiddleware` do Starlette
    processa handlers de `Exception` numa camada por fora do
    `CORSMiddleware` — sem devolver os cabeçalhos manualmente aqui, toda
    exceção não tratada saía sem eles, o navegador bloqueava a leitura
    da resposta e mostrava "erro de CORS" pro usuário (mascarando bugs
    inteiros em várias rotas diferentes, não só uma) em vez do `detalhe`
    de verdade que o handler já tratava direitinho."""

    def _explode(*args, **kwargs):
        raise RuntimeError("Falha simulada")

    monkeypatch.setattr(conta_service, "criar_lead", _explode)
    origem_permitida = settings.origens_cors[0]

    with TestClient(app, raise_server_exceptions=False) as cliente_tolerante:
        cliente_tolerante.headers.update(client.headers)
        resposta = cliente_tolerante.post(
            "/api/v1/leads/contas", json={"nome": "Empresa Teste"}, headers={"origin": origem_permitida}
        )

    assert resposta.status_code == 500
    assert resposta.headers.get("access-control-allow-origin") == origem_permitida


def test_erro_nao_tratado_nao_leva_cors_pra_origem_nao_permitida(client, monkeypatch):
    def _explode(*args, **kwargs):
        raise RuntimeError("Falha simulada")

    monkeypatch.setattr(conta_service, "criar_lead", _explode)

    with TestClient(app, raise_server_exceptions=False) as cliente_tolerante:
        cliente_tolerante.headers.update(client.headers)
        resposta = cliente_tolerante.post(
            "/api/v1/leads/contas", json={"nome": "Empresa Teste"}, headers={"origin": "https://site-nao-autorizado.com"}
        )

    assert resposta.status_code == 500
    assert "access-control-allow-origin" not in resposta.headers
