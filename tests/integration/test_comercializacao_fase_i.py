"""Phase I (plano unificado §45, OI-021, D-059): planos, módulos, entitlements, AI Credits, página de vendas.

- Só os preços aprovados; Public Procurement e a Suite seguem sem preço (nada inventado).
- "A partir de" (Enterprise) aparece no catálogo, nunca no checkout nem na lista de cadastro.
- A franquia do tier Enterprise substitui a do Strategic Sourcing (não soma) e cai na carteira única do tenant.
"""

from app.contexts.finops import contract as finops
from app.contexts.shared.entitlements import Entitlements
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider

TENANT = "tenant-teste"
D059 = (
    ("Bid Intelligence", 1490.0, None, ["bids"], True, "FIXED"),
    ("Strategic Sourcing", 2990.0, 5, ["sourcing"], True, "FIXED"),
    ("Strategic Sourcing Enterprise", 5990.0, None, ["sourcing", "sourcing_enterprise"], False, "STARTING_AT"),
)


def _semear(db_session) -> dict[str, Plano]:
    planos = {}
    for nome, preco, usuarios, modulos, self_service, tipo in D059:
        planos[nome] = Plano(nome=nome, franquia_contas_mes=0, max_usuarios=usuarios, preco_mensal=preco, visivel_self_service=self_service,
                             modulos_contratados=modulos, categoria="modulo", tipo_preco=tipo)
        db_session.add(planos[nome])
    db_session.commit()
    return planos


def test_pagina_de_vendas_mostra_as_linhas_com_os_precos_aprovados(client, db_session):
    _semear(db_session)
    catalogo = client.get("/api/v1/catalogo").json()
    produtos = {p["id"]: p for p in catalogo["produtos"]}
    assert (produtos["bid_intelligence"]["disponibilidade"], produtos["bid_intelligence"]["planos"]) == ("DISPONIVEL", ["Bid Intelligence"])
    assert (produtos["strategic_sourcing"]["disponibilidade"], produtos["strategic_sourcing"]["planos"]) == ("DISPONIVEL", ["Strategic Sourcing"])
    enterprise = produtos["strategic_sourcing_enterprise"]
    assert (enterprise["disponibilidade"], enterprise["status_preco"], enterprise["planos"]) == (
        "SOB_CONSULTA", "A_PARTIR_DE", ["Strategic Sourcing Enterprise"])
    assert produtos["public_procurement"]["disponibilidade"] == "EM_DEFINICAO"

    linhas = {linha["id"]: linha for linha in catalogo["linhas"]}
    assert [linha["id"] for linha in catalogo["linhas"]] == [
        "revenue_intelligence", "bid_intelligence", "public_procurement", "strategic_sourcing", "suite"]
    sourcing = {p["nome"]: p for p in linhas["strategic_sourcing"]["planos"]}
    assert (sourcing["Strategic Sourcing"]["preco_mensal"], sourcing["Strategic Sourcing"]["tipo_preco"],
            sourcing["Strategic Sourcing"]["max_usuarios"], sourcing["Strategic Sourcing"]["ai_credits_mensais"],
            sourcing["Strategic Sourcing"]["self_service"]) == (2990.0, "FIXED", 5, 50_000, True)
    assert (sourcing["Strategic Sourcing Enterprise"]["preco_mensal"], sourcing["Strategic Sourcing Enterprise"]["tipo_preco"],
            sourcing["Strategic Sourcing Enterprise"]["ai_credits_mensais"], sourcing["Strategic Sourcing Enterprise"]["self_service"]) == (
        5990.0, "STARTING_AT", 100_000, False)  # substitui os 50K, não soma
    bids = linhas["bid_intelligence"]
    assert [(p["preco_mensal"], p["ai_credits_mensais"]) for p in bids["planos"]] == [(1490.0, 25_000)]
    assert bids["pendencias"] == ["usuarios_incluidos"]  # o PO não definiu: a página mostra "a definir"
    for pendente in ("public_procurement", "suite"):
        assert (linhas[pendente]["planos"], linhas[pendente]["status_preco"]) == ([], "PENDING_DEFINITION")
    assert "R$" not in str(linhas["public_procurement"]) and "preco" in linhas["public_procurement"]["pendencias"]


def test_plano_com_procurement_nao_entra_na_venda_mesmo_por_engano(client, db_session):
    db_session.add(Plano(nome="Procurement por engano", franquia_contas_mes=0, preco_mensal=10.0, modulos_contratados=["procurement"]))
    db_session.commit()
    linhas = {linha["id"]: linha for linha in client.get("/api/v1/catalogo").json()["linhas"]}
    assert linhas["public_procurement"]["planos"] == []


def test_a_partir_de_nunca_vai_para_o_cadastro_self_service(client, db_session):
    planos = _semear(db_session)
    nomes = {p["nome"] for p in client.get("/api/v1/planos", params={"apenas_self_service": True}).json()}
    assert "Strategic Sourcing Enterprise" not in nomes and {"Bid Intelligence", "Strategic Sourcing"} <= nomes
    enterprise = planos["Strategic Sourcing Enterprise"]
    enterprise.visivel_self_service = True  # mesmo marcado por engano como self-service
    db_session.commit()
    nomes = {p["nome"] for p in client.get("/api/v1/planos", params={"apenas_self_service": True}).json()}
    assert "Strategic Sourcing Enterprise" not in nomes
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    resposta = client.post("/api/v1/auth/registrar-vitrine", json={
        "codigo_convite": convite["codigo"], "razao_social": "Compradora Enterprise Ltda", "nome_admin": "Admin",
        "email_admin": "admin@compradora-enterprise.com.br", "senha_admin": "senha123", "aceite_termos": True,
        "plano_id": enterprise.id})
    assert resposta.status_code == 409 and "self-service" in resposta.json()["detalhe"]


def test_entitlements_e_franquia_pelo_plano_real(client, db_session):
    planos = _semear(db_session)
    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT).one()
    provedor = NucleoPlanLimitsProvider(db_session)

    licenca.plano_id = planos["Strategic Sourcing"].id
    db_session.commit()
    direitos = Entitlements(provedor, TENANT)
    assert direitos.has_module("sourcing") and not direitos.has_module("bids") and not direitos.has_feature("SOURCING_ENTERPRISE")
    assert finops.carteira.franquia_do_tenant(db_session, TENANT)[0] == 50_000

    licenca.plano_id = planos["Strategic Sourcing Enterprise"].id
    db_session.commit()
    assert Entitlements(provedor, TENANT).has_feature("SOURCING_ENTERPRISE")
    assert finops.carteira.franquia_do_tenant(db_session, TENANT)[0] == 100_000

    licenca.plano_id = planos["Bid Intelligence"].id
    db_session.commit()
    direitos = Entitlements(provedor, TENANT)
    assert direitos.has_module("bids") and not direitos.has_module("sourcing") and not direitos.has_module("procurement")
    assert finops.carteira.franquia_do_tenant(db_session, TENANT)[0] == 25_000
