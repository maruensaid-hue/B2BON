"""Fluxo de convite: uso único sob concorrência, e-mail duplicado concorrente, validade, isolamento por tenant e enriquecimento via fila.

As corridas usam dois bancos de sessão sobre um ARQUIVO SQLite (conexões independentes) e disparam a segunda requisição dentro da janela
da primeira (entre a validação do convite e a gravação), que é exatamente onde o bug de uso único aparecia."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.coleta_site import ColetaSiteConta
from app.models.conta import Conta
from app.models.convite_cadastro import ConviteCadastro
from app.models.convite_vitrine import ConviteVitrine
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.providers.web_search.base import ResultadoBusca
from app.providers.payment.stub import StubPaymentProvider
from app.services import auth_service, enriquecimento_fila_service, tenant_service
from app.services.errors import RegraNegocioViolada
from tests.fakes import (
    FakeAccountDataProvider,
    FakeContactEnrichmentProvider,
    FakeGraphClient,
    FakeLLMProvider,
    FakeWebSearchProvider,
)

ORIGEM = "tenant-teste"
OUTRO = "tenant-convites-b"
B = "/api/v1/convites"


@pytest.fixture()
def bancos(tmp_path):
    """Fábrica de sessões independentes sobre o mesmo arquivo SQLite."""
    engine = create_engine(f"sqlite:///{tmp_path / 'convites.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine, autoflush=False)
    semente = fabrica()
    semente.add(Tenant(id="t-conv", razao_social="Empresa Convites"))
    semente.add(Tenant(id=ORIGEM, razao_social="Origem"))
    semente.commit()
    semente.close()
    yield fabrica
    engine.dispose()


def _convite_cadastro(fabrica, codigo="CODIGO-UNICO") -> None:
    with fabrica() as s:
        s.add(ConviteCadastro(tenant_id="t-conv", codigo=codigo, papel_concedido="user", status="disponivel"))
        s.commit()


def _durante_a_validacao(monkeypatch, acao):
    """Executa `acao()` uma única vez, logo depois da validação do convite da primeira requisição (antes de ela gravar)."""
    original = auth_service.validar_convite_disponivel
    estado = {"feito": False}

    def validar(db, convite, codigo):
        resultado = original(db, convite, codigo)
        if not estado["feito"]:
            estado["feito"] = True
            acao()
        return resultado

    monkeypatch.setattr(auth_service, "validar_convite_disponivel", validar)


# --- Uso único sob concorrência ------------------------------------------------------------------------------------------


def test_convite_de_cadastro_de_uso_unico_nao_vale_para_duas_requisicoes_simultaneas(bancos, monkeypatch):
    _convite_cadastro(bancos)
    sessao_a, sessao_b = bancos(), bancos()

    def segunda_requisicao():
        auth_service.registrar_com_convite(sessao_b, "CODIGO-UNICO", "Bia", "bia@convites.com.br", "senha123", True)

    _durante_a_validacao(monkeypatch, segunda_requisicao)

    with pytest.raises(RegraNegocioViolada, match="já utilizado"):
        auth_service.registrar_com_convite(sessao_a, "CODIGO-UNICO", "Ana", "ana@convites.com.br", "senha123", True)

    with bancos() as s:
        assert sorted(u.email for u in s.query(Usuario).filter_by(tenant_id="t-conv")) == ["bia@convites.com.br"]
        convite = s.query(ConviteCadastro).one()
        assert convite.status == "usado" and convite.usado_por_usuario_id is not None


def _plano(fabrica) -> int:
    with fabrica() as s:
        plano = Plano(nome="Plano Convite", franquia_contas_mes=500, max_usuarios=20, preco_mensal=499.0)
        s.add(plano)
        s.commit()
        return plano.id


def _criar_vitrine(sessao, codigo, razao, email, plano_id):
    return tenant_service.criar_tenant_vitrine(
        sessao, codigo, razao, "Admin", email, "senha123", True, plano_id, StubPaymentProvider(), FakeLLMProvider(),
        lambda d: "=== home ===\nx", FakeWebSearchProvider(), FakeAccountDataProvider(), FakeContactEnrichmentProvider(), FakeGraphClient(),
    )


def test_convite_vitrine_de_uso_unico_nao_cria_dois_tenants_na_corrida(bancos, monkeypatch):
    plano_id = _plano(bancos)
    with bancos() as s:
        codigo = tenant_service.gerar_convite_vitrine(s, ORIGEM, None, validade_horas=24).codigo
    sessao_a, sessao_b = bancos(), bancos()

    _durante_a_validacao(monkeypatch, lambda: _criar_vitrine(sessao_b, codigo, "Empresa Bia", "bia@vitrine.com.br", plano_id))

    with pytest.raises(RegraNegocioViolada, match="já utilizado"):
        _criar_vitrine(sessao_a, codigo, "Empresa Ana", "ana@vitrine.com.br", plano_id)

    with bancos() as s:
        assert s.query(Tenant).filter(Tenant.razao_social.in_(["Empresa Ana", "Empresa Bia"])).count() == 1
        assert s.query(Usuario).filter(Usuario.email.in_(["ana@vitrine.com.br", "bia@vitrine.com.br"])).count() == 1
        assert s.query(ConviteVitrine).one().tenant_id_gerado is not None


def test_email_duplicado_na_corrida_vira_erro_de_negocio_e_nao_consome_o_convite(bancos, monkeypatch):
    _convite_cadastro(bancos, "CONVITE-A")
    _convite_cadastro(bancos, "CONVITE-B")
    sessao_a, sessao_b = bancos(), bancos()
    original = auth_service._verificar_limite_de_usuarios
    estado = {"feito": False}

    def limite_com_concorrencia(db, tenant_id):
        original(db, tenant_id)
        if not estado["feito"]:  # o e-mail já passou pela checagem da requisição A; a B cadastra o mesmo e-mail agora
            estado["feito"] = True
            auth_service.registrar_com_convite(sessao_b, "CONVITE-B", "Bia", "mesmo@convites.com.br", "senha123", True)

    monkeypatch.setattr(auth_service, "_verificar_limite_de_usuarios", limite_com_concorrencia)

    with pytest.raises(RegraNegocioViolada, match="E-mail já cadastrado"):
        auth_service.registrar_com_convite(sessao_a, "CONVITE-A", "Ana", "mesmo@convites.com.br", "senha123", True)

    with bancos() as s:
        assert s.query(Usuario).filter_by(email="mesmo@convites.com.br").count() == 1
        assert s.query(ConviteCadastro).filter_by(codigo="CONVITE-A").one().status == "disponivel"  # rollback devolveu o convite


# --- Estados do convite -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["revogado", "usado", "expirado"])
def test_convite_que_nao_esta_disponivel_nao_cadastra_ninguem(bancos, status):
    with bancos() as s:
        s.add(ConviteCadastro(tenant_id="t-conv", codigo="X", papel_concedido="user", status=status))
        s.commit()
    with bancos() as s, pytest.raises(RegraNegocioViolada, match={"revogado": "revogado", "usado": "já utilizado", "expirado": "expirado"}[status]):
        auth_service.registrar_com_convite(s, "X", "Ana", "ana@convites.com.br", "senha123", True)
    with bancos() as s:
        assert s.query(Usuario).filter_by(tenant_id="t-conv").count() == 0


def test_convite_vencido_pelo_relogio_e_marcado_expirado_e_nao_cadastra(bancos):
    from datetime import UTC, datetime, timedelta

    with bancos() as s:
        s.add(ConviteCadastro(tenant_id="t-conv", codigo="VENCIDO", papel_concedido="user",
                              validade_em=(datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)))
        s.commit()
    with bancos() as s, pytest.raises(RegraNegocioViolada, match="expirado"):
        auth_service.registrar_com_convite(s, "VENCIDO", "Ana", "ana@convites.com.br", "senha123", True)
    with bancos() as s:
        assert s.query(ConviteCadastro).filter_by(codigo="VENCIDO").one().status == "expirado"
        assert s.query(Usuario).count() == 0


# --- Validade (API) ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rota", [B, f"{B}/vitrine"])
@pytest.mark.parametrize("horas", [0, -1, -168, 8761, 10**9, 10**12])
def test_validade_fora_do_intervalo_e_recusada_na_geracao(client, rota, horas):
    assert client.post(rota, json={"validade_horas": horas}).status_code == 422


@pytest.mark.parametrize("rota", [B, f"{B}/vitrine"])
@pytest.mark.parametrize("horas", [1, 168, 8760, None])
def test_validade_dentro_do_intervalo_ou_sem_prazo_continua_valendo(client, rota, horas):
    assert client.post(rota, json={"validade_horas": horas}).status_code == 201


# --- Isolamento entre tenants ------------------------------------------------------------------------------------------------


def test_outro_tenant_nao_ve_nem_altera_convites_alheios(client, criar_usuario_autenticado):
    cadastro = client.post(B, json={}).json()["codigo"]
    vitrine = client.post(f"{B}/vitrine", json={}).json()["codigo"]
    outro = criar_usuario_autenticado(OUTRO, papel="admin", email="admin@convites-b.com.br")

    assert client.get(B, headers=outro).json() == [] and client.get(f"{B}/vitrine", headers=outro).json() == []
    for metodo, rota in [("post", f"{B}/{cadastro}/revogar"), ("post", f"{B}/{cadastro}/reativar"), ("delete", f"{B}/{cadastro}"),
                         ("post", f"{B}/vitrine/{vitrine}/revogar"), ("post", f"{B}/vitrine/{vitrine}/reativar"),
                         ("delete", f"{B}/vitrine/{vitrine}")]:
        assert getattr(client, metodo)(rota, headers=outro).status_code == 404, rota
    assert [c["status"] for c in client.get(B).json()] == ["disponivel"]


def test_admin_comum_nao_gera_convite_de_super_admin(client, criar_usuario_autenticado):
    admin = criar_usuario_autenticado(ORIGEM, papel="admin", email="admin@convites-a.com.br")
    assert client.post(B, json={"papel_concedido": "super_admin"}, headers=admin).status_code == 403
    assert client.post(f"{B}/vitrine", json={"gratuito": True}, headers=criar_usuario_autenticado(
        ORIGEM, papel="user", email="user@convites-a.com.br")).status_code == 403


# --- Enriquecimento do convite de Rede Social (estava morto) -------------------------------------------------------------------


def test_convite_vitrine_enfileira_o_enriquecimento_e_a_fila_o_executa(db_session):
    db_session.add(Tenant(id="tenant-origem-vitrine", razao_social="Origem Vitrine"))
    plano = Plano(nome="Plano V", franquia_contas_mes=500, max_usuarios=20, preco_mensal=499.0)
    db_session.add(plano)
    db_session.commit()
    convite = tenant_service.gerar_convite_vitrine(db_session, "tenant-origem-vitrine", None, validade_horas=24)

    tenant_service.criar_tenant_vitrine(
        db_session, convite.codigo, "Empresa Convidada Ltda", "Admin", "admin@convidada-fila.com.br", "senha123", True, plano.id,
        StubPaymentProvider(), FakeLLMProvider(), lambda d: "=== home ===\nx", FakeWebSearchProvider(), FakeAccountDataProvider(),
        FakeContactEnrichmentProvider(), FakeGraphClient(), "11222333000181",
    )

    conta = db_session.query(Conta).filter_by(tenant_id="tenant-origem-vitrine", origem="rede_social_convite").one()
    item = db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta.id).one()
    assert (item.tenant_id, item.status) == ("tenant-origem-vitrine", "pendente")

    conta.dominio = "convidada.com.br"  # sem domínio a descoberta depende de busca na web; aqui o foco é a fila
    db_session.commit()
    site = lambda d: "=== https://convidada.com.br ===\nEmpresa Convidada. CNPJ 11.222.333/0001-81"  # noqa: E731
    resultado = enriquecimento_fila_service.processar_pendentes(
        db_session, FakeLLMProvider(["porte: media"]), site, FakeWebSearchProvider([ResultadoBusca(titulo="x", url="https://x.com", descricao="")]),
        FakeAccountDataProvider(), FakeGraphClient(), StubPlanLimitsProvider(),
    )

    assert resultado["concluidos"] == 1
    coleta = db_session.query(ColetaSiteConta).filter_by(conta_id=conta.id).one()
    assert (coleta.estado, coleta.dominio_situacao, coleta.disparo) == ("concluida", "confirmado", "fila")
