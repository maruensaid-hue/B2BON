from collections.abc import Generator

import os
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
    get_contact_enrichment_provider,
    get_crm_provider,
    get_db,
    get_sessao_factory,
    get_email_provider,
    get_email_provider_do_tenant,
    get_email_validation_provider,
    get_graph_client,
    get_llm_provider,
    get_mercado_client,
    get_noticias_client,
    get_payment_provider,
    get_plan_limits_provider,
    get_rede_social_provider,
    get_site_fetcher,
    get_web_search_provider,
    get_whatsapp_provider,
)
from app.api.v1.webhooks import _whatsapp_provider_do_webhook_email, _whatsapp_provider_do_webhook_whatsapp
from app.core.config import settings as _settings_webhooks
from app.core.rate_limit import limitador_api, limitador_auth, limitador_demo, limitador_ia, limitador_portal
from app.db.base import Base
from app.main import app
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.calendar.stub import StubCalendarProvider
from app.providers.crm.stub import StubCrmProvider
from app.providers.email_validation.stub import StubEmailVerificationProvider
from app.providers.payment.stub import StubPaymentProvider
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.providers.rede_social.stub import StubRedeSocialProvider
from app.services import auth_service, central_negocios_service
from tests.fakes import (
    FakeAccountDataProvider,
    FakeContactEnrichmentProvider,
    FakeEmailProvider,
    FakeGraphClient,
    FakeLLMProvider,
    FakeWebSearchProvider,
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
        plano = Plano(
            nome="Plano Padrão Teste",
            franquia_contas_mes=1000,
            max_usuarios=50,
            preco_mensal=0.0,
            modulos_contratados=["map", "predator", "crm"],
        )
        db_session.add(plano)
        db_session.flush()

    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db_session.commit()
# Onda A: autenticação real — o usuário de teste padrão é sempre o primeiro
# registro numa base em memória nova, então seu id (convertido para string
# por get_ator_id) é sempre "1", de forma determinística por teste.
ATOR_ID = "1"


SEGREDO_WEBHOOK_INTERNO_TESTE = "segredo-webhook-interno-teste"
APP_SECRET_META_TESTE = "app-secret-meta-teste"


@pytest.fixture(autouse=True)
def _segredos_de_webhook(monkeypatch):
    """Webhooks internos e o da Meta falham fechados sem segredo (V5.2.1): os testes configuram valores conhecidos."""
    monkeypatch.setattr(_settings_webhooks, "webhook_interno_secret", SEGREDO_WEBHOOK_INTERNO_TESTE)
    monkeypatch.setattr(_settings_webhooks, "whatsapp_app_secret", APP_SECRET_META_TESTE)


@pytest.fixture(autouse=True)
def _modo_creditos_medicao(monkeypatch):
    """Fase 15: a suíte mede créditos sem bloquear (MEASURE), para que
    testes de prompt/CRM não dependam de saldo. Testes de AI Credits usam
    a fixture `cobranca_ativa` (modo de produção, ENFORCE)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ai_creditos_modo", "MEASURE")


@pytest.fixture(autouse=True)
def _super_admin_segue_o_plano(monkeypatch):
    """O usuário padrão da fixture `client` é super_admin, e os testes de plano/módulo simulam um tenant SEM certos
    módulos por esse usuário. Em produção o super_admin ignora o plano (`super_admin_acesso_total_modulos`); aqui a
    chave começa desligada para esses testes continuarem validando o bloqueio por plano. Quem testa o acesso total
    liga a chave explicitamente (tests/integration/test_super_admin_acesso_total.py)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "super_admin_acesso_total_modulos", False)
    # Idem para a pesquisa de decisores: o usuário padrão dos testes é super_admin e os testes de limite precisam vê-lo sob o plano.
    monkeypatch.setattr(settings, "enriquecimento_super_admin_sem_limites", False)


@pytest.fixture(autouse=True)
def _ptax_sem_rede(monkeypatch):
    """D-076: a suíte nunca chama a API do Banco Central; sem cotação, a PTAX fica ausente (testes de câmbio injetam a
    busca ou cadastram a cotação)."""
    from app.contexts.finops import cambio

    monkeypatch.setattr(cambio, "_buscar_ptax_bcb", lambda dia: None)


@pytest.fixture(autouse=True)
def _sourcing_leitura_dupla_estrita(monkeypatch):
    """Sourcing S3: toda leitura de licitação/processo/documento/requisito na
    suíte confere as tabelas unificadas e falha em qualquer divergência — é
    assim que a paridade é provada teste a teste."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "ESTRITA")


@pytest.fixture()
def cobranca_ativa(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ai_creditos_modo", "ENFORCE")


_PG_RLS_URL = os.environ.get("B2BON_TESTE_PG_RLS_URL")


@pytest.fixture(scope="session")
def _bancos_pg_rls():
    """Modo opcional (D-111): os mesmos testes HTTP, só que contra PostgreSQL de verdade com o RLS ligado. Ligado por `B2BON_TESTE_PG_RLS_URL` (servidor onde se possa criar banco e papel).

    O teste semeia e confere com o DONO das tabelas (que não passa pelo RLS); cada requisição HTTP usa uma sessão do papel de EXECUÇÃO (sem superusuário, sem BYPASSRLS), como em
    produção. Pega o que a sonda não vê: consulta que, sob o RLS, devolve menos linhas sem dar erro. Sem a variável, não faz nada e a suíte segue em SQLite."""
    if not _PG_RLS_URL:
        yield None
        return
    import secrets
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from app.db import rls_sql

    sufixo = secrets.token_hex(4)
    nome_banco, papel, senha = f"b2bon_suite_{sufixo}", f"b2bon_suite_app_{sufixo}", secrets.token_urlsafe(24)
    base = make_url(_PG_RLS_URL)
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conexao:
        conexao.execute(text(f'CREATE DATABASE "{nome_banco}"'))
    url_dono = base.set(database=nome_banco)
    ambiente = {
        **os.environ,
        "DATABASE_URL": url_dono.render_as_string(hide_password=False),
        "CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",  # só para a migração rodar; chave de teste, sem valor
    }
    ambiente.pop("MIGRATION_DATABASE_URL", None)
    resultado = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=Path(__file__).resolve().parents[1], env=ambiente, capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    dono = create_engine(url_dono)
    from sqlalchemy import event

    @event.listens_for(dono, "connect")
    def _sem_chave_estrangeira_no_semeio(conexao_dbapi, _registro):
        # O SQLite dos testes não aplica chave estrangeira (vários testes semeiam linha de tenant que nem existe); na conexão do DONO (que semeia e confere) o PostgreSQL
        # também não aplica. A conexão do papel de execução (a da requisição) continua aplicando tudo, como em produção.
        cursor = conexao_dbapi.cursor()
        cursor.execute("SET session_replication_role = replica")
        cursor.close()
        conexao_dbapi.commit()

    with dono.begin() as conexao:
        for comando in rls_sql.sql_papel_aplicacao(papel, senha):
            conexao.execute(text(comando))
    # `lock_timeout`: se algum teste ainda segurar um lock, a requisição falha em segundos em vez de travar a suíte inteira.
    app_engine = create_engine(url_dono.set(username=papel, password=senha), pool_pre_ping=True, connect_args={"options": "-c lock_timeout=5000"})
    consulta_nao_vazias = " UNION ALL ".join(f"SELECT '{t}' WHERE EXISTS (SELECT 1 FROM \"{t}\")" for t in Base.metadata.tables)
    yield {"dono": dono, "app": app_engine, "consulta_nao_vazias": consulta_nao_vazias}
    app_engine.dispose()
    dono.dispose()
    with admin.connect() as conexao:
        conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome_banco}" WITH (FORCE)'))
        conexao.execute(text(f"DROP ROLE IF EXISTS {papel}"))
    admin.dispose()


@pytest.fixture()
def db_session(_bancos_pg_rls) -> Generator[Session, None, None]:
    if _bancos_pg_rls is not None:
        from sqlalchemy import text

        # Sessão do DONO para o teste semear e conferir; a limpeza entre testes também é do dono (o papel de execução não tem TRUNCATE).
        session = sessionmaker(autocommit=False, autoflush=False, bind=_bancos_pg_rls["dono"])()
        session.info["pg_app_engine"] = _bancos_pg_rls["app"]
        try:
            yield session
        finally:
            session.rollback()
            session.close()
            # Truncar as 200+ tabelas a cada teste custa segundos; trunca só as que têm linha e zera só as sequências que andaram (os testes contam com ids que recomeçam em 1).
            with _bancos_pg_rls["dono"].begin() as conexao:
                nao_vazias = [linha[0] for linha in conexao.execute(text(_bancos_pg_rls["consulta_nao_vazias"])).all()]
                if nao_vazias:
                    # `replica` desliga os gatilhos de chave estrangeira nesta transação (precisa de superusuário, que é o dono do banco descartável): DELETE em qualquer ordem, sem a
                    # troca de arquivos do TRUNCATE.
                    conexao.execute(text("SET LOCAL session_replication_role = replica"))
                    for tabela in nao_vazias:
                        conexao.execute(text(f'DELETE FROM "{tabela}"'))
                for (sequencia,) in conexao.execute(text("SELECT schemaname || '.' || sequencename FROM pg_sequences WHERE last_value IS NOT NULL")).all():
                    conexao.execute(text(f"SELECT setval('{sequencia}', 1, false)"))
        return
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
def fake_contact_enrichment() -> FakeContactEnrichmentProvider:
    return FakeContactEnrichmentProvider()


@pytest.fixture()
def fake_web_search() -> FakeWebSearchProvider:
    return FakeWebSearchProvider()


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
def fake_mercado_client():
    return lambda: {
        "indices": [{"nome": "Ibovespa", "pontos": 130000.5, "variacao_pct": 1.23, "serie": [{"data": "21/09", "valor": 130000.5}]}],
        "cambio": [
            {"codigo": "USD", "nome": "USD", "valor": 5.05, "variacao_pct": -0.5},
            {"codigo": "BTC", "nome": "Bitcoin", "valor": 444552.0, "variacao_pct": 6.47},
        ],
    }


@pytest.fixture()
def fake_noticias_client():
    return lambda: [
        {"portal": "UOL Economia", "titulo": "Manchete de teste", "link": "https://exemplo.com/1", "publicado_em": None},
    ]


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
def fake_payment() -> StubPaymentProvider:
    return StubPaymentProvider()


@pytest.fixture()
def client(
    db_session: Session,
    fake_graph: FakeGraphClient,
    fake_llm: FakeLLMProvider,
    fake_account_data: FakeAccountDataProvider,
    fake_contact_enrichment: FakeContactEnrichmentProvider,
    fake_web_search: FakeWebSearchProvider,
    fake_plan_limits: StubPlanLimitsProvider,
    fake_site_fetcher,
    fake_brasilapi_client,
    fake_mercado_client,
    fake_noticias_client,
    fake_whatsapp: FakeWhatsAppProvider,
    fake_email: FakeEmailProvider,
    fake_calendar: StubCalendarProvider,
    fake_crm: StubCrmProvider,
    fake_rede_social: StubRedeSocialProvider,
    fake_email_validacao: StubEmailVerificationProvider,
    fake_payment: StubPaymentProvider,
) -> Generator[TestClient, None, None]:
    limitador_auth.resetar()  # a suíte inteira roda no mesmo processo — sem isto, um teste vaza rate-limit pro próximo
    limitador_ia.resetar()
    limitador_api.resetar()
    limitador_portal.resetar()
    limitador_demo.resetar()
    from app.contexts.intelligence.gateway import limitador_automatico

    limitador_automatico.resetar()
    central_negocios_service.resetar_cache()

    def override_get_db() -> Generator[Session, None, None]:
        engine_app = db_session.info.get("pg_app_engine")
        if engine_app is not None:  # modo PostgreSQL com RLS: sessão própria do papel de execução por requisição, como em produção
            sessao = sessionmaker(autocommit=False, autoflush=False, bind=engine_app)()
            try:
                yield sessao
            finally:
                sessao.close()
            return
        # Em produção cada requisição tem sessão própria e nasce sem contexto de RLS; aqui a sessão é compartilhada com a fixture, então zera o contexto herdado.
        db_session.info.pop("rls_contexto", None)
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Reserva de demonstrações (D-085) não roda em segundo plano nos testes; test_demonstracao a exercita direto.
    app.dependency_overrides[get_sessao_factory] = lambda: None
    app.dependency_overrides[get_graph_client] = lambda: fake_graph
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_account_data_provider] = lambda: fake_account_data
    app.dependency_overrides[get_contact_enrichment_provider] = lambda: fake_contact_enrichment
    app.dependency_overrides[get_web_search_provider] = lambda: fake_web_search
    app.dependency_overrides[get_plan_limits_provider] = lambda: fake_plan_limits
    app.dependency_overrides[get_site_fetcher] = lambda: fake_site_fetcher
    app.dependency_overrides[get_brasilapi_client] = lambda: fake_brasilapi_client
    app.dependency_overrides[get_mercado_client] = lambda: fake_mercado_client
    app.dependency_overrides[get_noticias_client] = lambda: fake_noticias_client
    app.dependency_overrides[get_whatsapp_provider] = lambda: fake_whatsapp
    app.dependency_overrides[_whatsapp_provider_do_webhook_whatsapp] = lambda: fake_whatsapp
    app.dependency_overrides[_whatsapp_provider_do_webhook_email] = lambda: fake_whatsapp
    app.dependency_overrides[get_email_provider] = lambda: fake_email
    app.dependency_overrides[get_email_provider_do_tenant] = lambda: fake_email
    app.dependency_overrides[get_calendar_provider] = lambda: fake_calendar
    app.dependency_overrides[get_crm_provider] = lambda: fake_crm
    app.dependency_overrides[get_rede_social_provider] = lambda: fake_rede_social
    app.dependency_overrides[get_email_validation_provider] = lambda: fake_email_validacao
    app.dependency_overrides[get_payment_provider] = lambda: fake_payment

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
        test_client.headers.update({"Authorization": f"Bearer {token}", "X-Webhook-Secret": SEGREDO_WEBHOOK_INTERNO_TESTE})
        if db_session.info.get("pg_app_engine") is not None:
            # Modo PostgreSQL com RLS: o teste semeia numa sessão e a requisição usa outra. No SQLite a sessão é uma só, então o que o teste já gravou vale para a requisição;
            # aqui o semeio é confirmado antes de cada chamada (e o que a requisição gravou é relido depois).
            requisicao_original = test_client.request

            def requisicao_com_semeio_confirmado(*args, **kwargs):
                db_session.commit()
                try:
                    return requisicao_original(*args, **kwargs)
                finally:
                    db_session.expire_all()

            test_client.request = requisicao_com_semeio_confirmado
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def tenants_da_rede(db_session: Session) -> None:
    """Fase 7: relacionamentos da rede ligam identidades de empresas reais,
    então os testes de serviço precisam das linhas de `tenant` (em Postgres
    a FK já exigia isso; o SQLite dos testes não aplica FK)."""
    for tenant_id in ("tenant-teste", "tenant-outro", "tenant-terceiro"):
        if db_session.get(Tenant, tenant_id) is None:
            db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}"))
    db_session.commit()


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
def criar_plano(db_session: Session):
    def _criar(**overrides: object) -> Plano:
        dados = {
            "nome": f"Plano Teste {db_session.query(Plano).count() + 1}",
            "franquia_contas_mes": 500,
            "max_usuarios": 20,
            "preco_mensal": 499.0,
            "modulos_contratados": ["map", "predator", "crm"],
        }
        dados.update(overrides)
        plano = Plano(**dados)
        db_session.add(plano)
        db_session.commit()
        return plano

    return _criar


@pytest.fixture()
def criar_representante(db_session: Session):
    def _criar(**overrides: object) -> Representante:
        numero = db_session.query(Representante).count() + 1
        dados = {
            "nome": f"Representante Teste {numero}",
            "email": f"representante{numero}@teste.com.br",
            "chave_pix": f"pix-representante{numero}@teste.com.br",
            "percentual_comissao": 0.1,
        }
        dados.update(overrides)
        representante = Representante(**dados)
        db_session.add(representante)
        db_session.commit()
        return representante

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
                # Raio-X 2026-09-15: só 1 toque de WhatsApp por cadência é
                # permitido (o de ordem 2, acima) — este é e-mail, não
                # whatsapp de novo.
                {"ordem": 5, "canal": "email", "intervalo_dias_apos_anterior": 3},
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
                {"ordem": 5, "canal": "email", "intervalo_dias_apos_anterior": 7},
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


@pytest.fixture(autouse=True)
def _disjuntor_ia_fechado():
    """O disjuntor do gateway é estado de processo: nenhum teste herda o circuito aberto de outro."""
    from app.contexts.intelligence.disjuntor import disjuntor_ia

    from app.llm import fallback

    disjuntor_ia.reiniciar()
    fallback.reiniciar_disjuntores()
    yield
    disjuntor_ia.reiniciar()
    fallback.reiniciar_disjuntores()


def pytest_configure(config):
    if os.environ.get("B2BON_RLS_SONDA"):
        from tests import rls_sonda

        rls_sonda.ativar()


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("B2BON_RLS_SONDA"):
        from tests import rls_sonda

        rls_sonda.gravar_relatorio()
