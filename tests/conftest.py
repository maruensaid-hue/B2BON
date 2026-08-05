from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registra as tabelas em Base.metadata
from app.api.deps import (
    get_account_data_provider,
    get_brasilapi_client,
    get_calendar_provider,
    get_crm_provider,
    get_db,
    get_email_provider,
    get_email_validation_provider,
    get_graph_client,
    get_llm_provider,
    get_plan_limits_provider,
    get_rede_social_provider,
    get_site_fetcher,
    get_whatsapp_provider,
)
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.calendar.stub import StubCalendarProvider
from app.providers.crm.stub import StubCrmProvider
from app.providers.email_validation.stub import StubEmailVerificationProvider
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.providers.rede_social.stub import StubRedeSocialProvider
from app.services import auth_service
from tests.fakes import (
    FakeAccountDataProvider,
    FakeEmailProvider,
    FakeGraphClient,
    FakeLLMProvider,
    FakeWhatsAppProvider,
)

TENANT_ID = "tenant-teste"


def _garantir_licenca_ativa(db_session: Session, tenant_id: str) -> None:
    """Toda conta de teste padrão representa um cliente pagante — só os
    testes do fluxo de convite-vitrine (Onda H) criam tenant de propósito
    sem licença. Idempotente: get-or-create em cada tabela."""
    if db_session.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}"))
        db_session.flush()

    if db_session.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none() is not None:
        return

    plano = db_session.query(Plano).filter_by(nome="Plano Padrão Teste").one_or_none()
    if plano is None:
        plano = Plano(nome="Plano Padrão Teste", franquia_contas_mes=1000, max_usuarios=50, preco_mensal=0.0)
        db_session.add(plano)
        db_session.flush()

    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db_session.commit()
# Onda A: autenticação real — o usuário de teste padrão é sempre o primeiro
# registro numa base em memória nova, então seu id (convertido para string
# por get_ator_id) é sempre "1", de forma determinística por teste.
ATOR_ID = "1"


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
    return lambda dominio: (
        f"=== https://{dominio} ===\n<html>Site institucional de {dominio}: "
        "empresa de tecnologia de porte médio.</html>"
    )


@pytest.fixture()
def fake_brasilapi_client():
    return lambda cnpj: {"ddd_telefone_1": "11987654321", "email": f"contato@{cnpj}.com.br"}


@pytest.fixture()
def fake_whatsapp() -> FakeWhatsAppProvider:
    return FakeWhatsAppProvider()


@pytest.fixture()
def fake_email() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture()
def fake_calendar() -> StubCalendarProvider:
    return StubCalendarProvider()


@pytest.fixture()
def fake_crm() -> StubCrmProvider:
    return StubCrmProvider()


@pytest.fixture()
def fake_rede_social() -> StubRedeSocialProvider:
    return StubRedeSocialProvider()


@pytest.fixture()
def fake_email_validacao() -> StubEmailVerificationProvider:
    return StubEmailVerificationProvider()


@pytest.fixture()
def client(
    db_session: Session,
    fake_graph: FakeGraphClient,
    fake_llm: FakeLLMProvider,
    fake_account_data: FakeAccountDataProvider,
    fake_plan_limits: StubPlanLimitsProvider,
    fake_site_fetcher,
    fake_brasilapi_client,
    fake_whatsapp: FakeWhatsAppProvider,
    fake_email: FakeEmailProvider,
    fake_calendar: StubCalendarProvider,
    fake_crm: StubCrmProvider,
    fake_rede_social: StubRedeSocialProvider,
    fake_email_validacao: StubEmailVerificationProvider,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_graph_client] = lambda: fake_graph
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_account_data_provider] = lambda: fake_account_data
    app.dependency_overrides[get_plan_limits_provider] = lambda: fake_plan_limits
    app.dependency_overrides[get_site_fetcher] = lambda: fake_site_fetcher
    app.dependency_overrides[get_brasilapi_client] = lambda: fake_brasilapi_client
    app.dependency_overrides[get_whatsapp_provider] = lambda: fake_whatsapp
    app.dependency_overrides[get_email_provider] = lambda: fake_email
    app.dependency_overrides[get_calendar_provider] = lambda: fake_calendar
    app.dependency_overrides[get_crm_provider] = lambda: fake_crm
    app.dependency_overrides[get_rede_social_provider] = lambda: fake_rede_social
    app.dependency_overrides[get_email_validation_provider] = lambda: fake_email_validacao

    _garantir_licenca_ativa(db_session, TENANT_ID)

    usuario_teste = Usuario(
        tenant_id=TENANT_ID,
        nome="Usuário Teste",
        email="teste@tenant-teste.com.br",
        papel="super_admin",
        ativo=True,
    )
    db_session.add(usuario_teste)
    db_session.commit()
    token = auth_service.gerar_token(usuario_teste)

    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def criar_usuario_autenticado(db_session: Session):
    """Cria um usuário (de um tenant qualquer) e devolve os headers de
    autenticação prontos — usado por testes que precisam de um segundo
    tenant além do padrão da fixture `client` (ex.: isolamento multi-tenant
    do E8-H3)."""

    def _criar(tenant_id: str, papel: str = "admin", email: str | None = None) -> dict[str, str]:
        _garantir_licenca_ativa(db_session, tenant_id)
        usuario = Usuario(
            tenant_id=tenant_id,
            nome=f"Usuário {tenant_id}",
            email=email or f"user@{tenant_id}.com.br",
            papel=papel,
            ativo=True,
        )
        db_session.add(usuario)
        db_session.commit()
        token = auth_service.gerar_token(usuario)
        return {"Authorization": f"Bearer {token}"}

    return _criar


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


@pytest.fixture()
def configurar_comunicacao(client: TestClient):
    def _configurar(**overrides: object) -> dict:
        payload = {"tom": "consultivo", "restricoes": []}
        payload.update(overrides)
        resposta = client.put("/api/v1/comunicacao", json=payload)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    return _configurar


@pytest.fixture()
def onboarding_completo(criar_icp, criar_oferta, configurar_comunicacao):
    """E3 depende de ICP + oferta + comunicação já configurados (E1)."""
    criar_icp()
    criar_oferta()
    configurar_comunicacao()


@pytest.fixture()
def criar_conta_com_decisor(db_session: Session, criar_icp):
    def _criar(**overrides: object) -> tuple[Conta, Decisor]:
        icp = criar_icp()
        conta = Conta(tenant_id=TENANT_ID, icp_id=icp["id"], nome="Conta Teste", status="prospectada")
        db_session.add(conta)
        db_session.flush()

        dados_decisor = {
            "nome": "Decisor Teste",
            "cargo": "CEO",
            "email": "decisor@empresateste.com.br",
            "telefone": "+5511999999999",
            "linkedin_url": "https://linkedin.com/in/decisor-teste",
        }
        dados_decisor.update(overrides)
        decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, **dados_decisor)
        db_session.add(decisor)
        db_session.commit()
        return conta, decisor

    return _criar


@pytest.fixture()
def criar_cadencia(client: TestClient):
    def _criar(**overrides: object) -> dict:
        payload = {
            "nome": "Cadência Teste",
            "toques": [
                {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
                {
                    "ordem": 2,
                    "canal": "whatsapp",
                    "intervalo_dias_apos_anterior": 2,
                    "template_whatsapp_id": "prospeccao_inicial",
                },
                {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 3},
                {"ordem": 4, "canal": "linkedin", "intervalo_dias_apos_anterior": 2},
                {
                    "ordem": 5,
                    "canal": "whatsapp",
                    "intervalo_dias_apos_anterior": 3,
                    "template_whatsapp_id": "prospeccao_inicial",
                },
            ],
        }
        payload.update(overrides)
        resposta = client.post("/api/v1/cadencias", json=payload)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    return _criar


@pytest.fixture()
def criar_cadencia_nutricao(client: TestClient):
    def _criar(**overrides: object) -> dict:
        payload = {
            "nome": "Nutrição Teste",
            "tipo": "nutricao",
            "toques": [
                {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
                {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 7, "template_whatsapp_id": "x"},
                {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 7},
                {"ordem": 4, "canal": "linkedin", "intervalo_dias_apos_anterior": 7},
                {"ordem": 5, "canal": "whatsapp", "intervalo_dias_apos_anterior": 7, "template_whatsapp_id": "x"},
            ],
        }
        payload.update(overrides)
        resposta = client.post("/api/v1/cadencias", json=payload)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    return _criar


@pytest.fixture()
def configurar_notificacao(client: TestClient):
    def _configurar(**overrides: object) -> dict:
        payload = {"vendedor_id": "vendedor-1", "vendedor_telefone": "+5511988887777"}
        payload.update(overrides)
        resposta = client.put("/api/v1/notificacoes/configuracao", json=payload)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    return _configurar
