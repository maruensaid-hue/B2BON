from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registra as tabelas em Base.metadata
from app.api.deps import (
    get_account_data_provider,
    get_db,
    get_graph_client,
    get_llm_provider,
    get_plan_limits_provider,
    get_site_fetcher,
)
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from tests.fakes import FakeAccountDataProvider, FakeGraphClient, FakeLLMProvider

TENANT_ID = "tenant-teste"
ATOR_ID = "user-teste"


@pytest.fixture(autouse=True)
def _isolar_storage_de_materiais(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Materiais enviados em teste nunca devem tocar ./storage do projeto."""
    monkeypatch.setattr(settings, "materiais_storage_path", str(tmp_path / "materiais"))


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    # StaticPool: o TestClient roda os endpoints em outra thread (via
    # anyio.to_thread); sem StaticPool cada thread pegaria uma conexão
    # nova do pool, e SQLite `:memory:` sem StaticPool = um banco vazio
    # diferente por conexão.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def fake_graph() -> FakeGraphClient:
    return FakeGraphClient()


@pytest.fixture()
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture()
def fake_account_data() -> FakeAccountDataProvider:
    return FakeAccountDataProvider()


@pytest.fixture()
def fake_plan_limits() -> StubPlanLimitsProvider:
    return StubPlanLimitsProvider(franquia_padrao=1000)


@pytest.fixture()
def fake_site_fetcher():
    return lambda dominio: f"<html>Site institucional de {dominio}: empresa de tecnologia de porte médio.</html>"


@pytest.fixture()
def client(
    db_session: Session,
    fake_graph: FakeGraphClient,
    fake_llm: FakeLLMProvider,
    fake_account_data: FakeAccountDataProvider,
    fake_plan_limits: StubPlanLimitsProvider,
    fake_site_fetcher,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_graph_client] = lambda: fake_graph
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_account_data_provider] = lambda: fake_account_data
    app.dependency_overrides[get_plan_limits_provider] = lambda: fake_plan_limits
    app.dependency_overrides[get_site_fetcher] = lambda: fake_site_fetcher

    with TestClient(app) as test_client:
        test_client.headers.update({"X-Tenant-Id": TENANT_ID, "X-User-Id": ATOR_ID})
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def criar_icp(client: TestClient):
    def _criar(**overrides: object) -> dict:
        payload = {
            "nome": "ICP Teste",
            "segmento": "Tecnologia",
            "porte": "PEQUENO",
            "regiao": "SP",
            "dores": ["dor1"],
            "gatilhos": ["gatilho1"],
            "cnae_codigos": ["6201500"],
            "ufs": ["SP"],
        }
        payload.update(overrides)
        resposta = client.post("/api/v1/icp", json=payload)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    return _criar


@pytest.fixture()
def criar_oferta(client: TestClient):
    def _criar(**overrides: object) -> dict:
        payload = {
            "nome": "Oferta Teste",
            "descricao": "Descrição da oferta",
            "diferenciais": ["diferencial1"],
            "provas_sociais": ["prova1"],
        }
        payload.update(overrides)
        resposta = client.post("/api/v1/ofertas", json=payload)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    return _criar
