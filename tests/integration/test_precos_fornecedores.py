"""D-077: preços públicos verificados dos fornecedores (2026-10-01) no Infrastructure Cost Pool — maior plano público
APLICÁVEL à arquitetura real, Capacity Envelope para preço por uso, nada de preço inventado para planos CUSTOM, sem dupla
contagem entre pools, conversão pela PTAX e capacidade não alocada identificável."""

import importlib.util
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.comissoes import contract as comissoes
from app.contexts.finops import contract as finops
from app.models.custo_infraestrutura import ComponenteInfra
from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.services.errors import ValidacaoFalhou

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mig_d077", RAIZ / "alembic/versions/c8e0a2b4d6f9_precos_publicos_fornecedores.py")
MIG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MIG)
DIA = date(2026, 10, 15)
POOLS = ["INFRASTRUCTURE", "DATA_PROVIDER"]


def _semear(db):
    """Os componentes da migração (a fonte de produção) e o benchmark do Neon."""
    for dados in MIG.COMPONENTES:
        comissoes.infraestrutura.criar(db, {k: v for k, v in dados.items() if k != "criado_por"}, "teste")
    neon = _componente(db, "NEON", "POSTGRES")
    comissoes.infraestrutura.criar_envelope(db, neon.id, {k: v for k, v in MIG.BENCHMARK_NEON.items() if k != "moeda"}, "teste")
    finops.cambio.registrar(db, {"moeda_base": "USD", "moeda_cotacao": "BRL", "taxa": 5.0, "fonte": "BANCO_CENTRAL_DO_BRASIL",
                                 "tipo": "PTAX_CLOSE", "data_cotacao": DIA - timedelta(days=1)}, "teste")
    db.commit()


def _componente(db, fornecedor, servico) -> ComponenteInfra:
    return db.query(ComponenteInfra).filter_by(fornecedor=fornecedor, servico=servico).one()


def _envelope_neon(db, horas=730, gb=100):
    return comissoes.infraestrutura.criar_envelope(db, _componente(db, "NEON", "POSTGRES").id, {
        "horas_computo_provisionadas": horas, "armazenamento_gb_provisionado": gb, "vigente_de": MIG.INICIO, "fonte": "decisão de teste"}, "teste")


def _tenant(db, tenant_id, tier):
    plano = Plano(nome=f"Plano {tenant_id}", franquia_contas_mes=0, preco_mensal=1000.0, modulos_contratados=["crm"], tier_infraestrutura=tier)
    db.add_all([plano, Tenant(id=tenant_id, razao_social=tenant_id)])
    db.flush()
    db.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db.commit()
    return plano


def test_precos_publicos_verificados_do_render_e_da_lusha():
    por_servico = {(c["fornecedor"], c["servico"]): c for c in MIG.COMPONENTES}
    workspace, web = por_servico[("RENDER", "WORKSPACE")], por_servico[("RENDER", "WEB_SERVICE_COMPUTE")]
    assert (workspace["plano_referencia"], workspace["custo_referencia"], workspace["moeda"], workspace["ciclo_cobranca"]) == (
        "Scale", 499.00, "USD", "MONTHLY")
    assert (web["plano_referencia"], web["custo_referencia"]) == ("12c-96g", 1500.00)
    lusha = por_servico[("LUSHA", "SALES_INTELLIGENCE")]
    assert (lusha["plano_referencia"], lusha["custo_referencia"], lusha["contabilizacao"]) == ("Premium", 399.90, "DATA_PROVIDER")
    assert (lusha["atributos"]["creditos_incluidos"], lusha["atributos"]["assentos_incluidos"]) == (3400, 5)
    for chave in (("RENDER", "WORKSPACE_ENTERPRISE"), ("LUSHA", "SALES_INTELLIGENCE_SCALE")):
        custom = por_servico[chave]
        assert (custom["modelo_preco"], custom["custo_referencia"], custom["custo_contratado"]) == ("CUSTOM", None, None)  # nada inventado
    for componente in MIG.COMPONENTES:
        assert (componente["tipo_fonte"], componente["verificado_em"]) == ("OFFICIAL_PUBLIC_PRICING", date(2026, 10, 1))
        assert componente["url_fonte"].startswith("https://") and componente["proxima_revisao_em"] > componente["verificado_em"]


def test_pool_so_com_componentes_aplicaveis_e_postgres_e_key_value_fora(db_session):
    _semear(db_session)
    no_pool = {(c.fornecedor, c.servico) for c in comissoes.infraestrutura.aplicaveis(db_session, DIA, POOLS)}
    assert no_pool == {("RENDER", "WORKSPACE"), ("RENDER", "WEB_SERVICE_COMPUTE"), ("NEON", "POSTGRES"), ("LUSHA", "SALES_INTELLIGENCE")}
    assert ("RENDER", "POSTGRES") not in no_pool  # USD 11.000 nunca entra sozinho
    key_value = _componente(db_session, "RENDER", "KEY_VALUE")
    comissoes.infraestrutura.atualizar(db_session, key_value.id, {"status_arquitetura": "APPLICABLE", "provisionado_para_comissao": True},
                                       "Arquitetura passou a usar Key Value", "teste")
    assert ("RENDER", "KEY_VALUE") in {(c.fornecedor, c.servico) for c in comissoes.infraestrutura.aplicaveis(db_session, DIA, POOLS)}


def test_neon_por_uso_sem_envelope_aguarda_e_benchmark_nunca_vira_custo(db_session):
    _semear(db_session)
    neon = _componente(db_session, "NEON", "POSTGRES")
    custos = comissoes.infraestrutura.custos_mensais(db_session, neon, DIA)
    assert (custos["provisionado"], custos["faltante"]) == (None, "INFRASTRUCTURE_COST")  # o USD 1.404 é só benchmark
    assert comissoes.infraestrutura.pool(db_session, DIA)["faltantes"] == ["INFRASTRUCTURE_COST"]
    envelope = _envelope_neon(db_session, horas=730, gb=100)  # quantidades de teste (decisão da CyberFort)
    assert envelope.custo_mensal_estimado == Decimal("197.06")  # 730 × 0,222 + 100 × 0,35
    custos = comissoes.infraestrutura.custos_mensais(db_session, neon, DIA)
    assert custos["provisionado"] == Decimal("985.30")  # USD 197,06 × PTAX 5,00
    with pytest.raises(ValidacaoFalhou, match="horas"):
        comissoes.infraestrutura.criar_envelope(db_session, neon.id, {"armazenamento_gb_provisionado": 10}, "teste")
    with pytest.raises(ValidacaoFalhou, match="USAGE_BASED"):
        comissoes.infraestrutura.criar_envelope(db_session, _componente(db_session, "RENDER", "WORKSPACE").id,
                                                {"horas_computo_provisionadas": 1, "armazenamento_gb_provisionado": 1}, "teste")


def test_dolar_pela_ptax_e_pool_completo_com_envelope(db_session):
    _semear(db_session)
    _envelope_neon(db_session)
    dados = comissoes.infraestrutura.pool(db_session, DIA)
    # (499 + 1.500) × 5 = 9.995 infraestrutura + 985,30 Neon; Lusha 399,90 × 5 = 1.999,50 provedor de dados
    assert dados["por_pool"] == {"DATA_PROVIDER": 1999.5, "INFRASTRUCTURE": 10980.3}
    assert dados["provisionado"] == Decimal("12979.80") and dados["faltantes"] == []
    fx = next(c for c in dados["componentes"] if c["servico"] == "WORKSPACE")["fx"]
    assert (fx["fx_rate"], fx["source"], fx["type"]) == (5.0, "BANCO_CENTRAL_DO_BRASIL", "PTAX_CLOSE")


def test_sem_ptax_custos_em_dolar_aguardam(db_session):
    for dados in MIG.COMPONENTES[:2]:
        comissoes.infraestrutura.criar(db_session, {k: v for k, v in dados.items() if k != "criado_por"}, "teste")
    assert comissoes.infraestrutura.pool(db_session, DIA)["faltantes"] == ["FX_RATE"]


def test_sem_dupla_contagem_neon_e_render_postgres(db_session):
    _semear(db_session)
    postgres = _componente(db_session, "RENDER", "POSTGRES")
    with pytest.raises(ValidacaoFalhou, match="PRIMARY_DATABASE"):
        comissoes.infraestrutura.atualizar(db_session, postgres.id, {"status_arquitetura": "APPLICABLE", "provisionado_para_comissao": True},
                                           "teste", "teste")
    db_session.rollback()
    comissoes.infraestrutura.atualizar(db_session, _componente(db_session, "RENDER", "POSTGRES").id,
                                       {"status_arquitetura": "APPLICABLE", "provisionado_para_comissao": True,
                                        "coexistencia_justificada": "Réplica analítica em uso real"}, "Uso real dos dois", "teste")
    assert len([c for c in comissoes.infraestrutura.aplicaveis(db_session, DIA, POOLS) if c.funcao_arquitetural == "PRIMARY_DATABASE"]) == 2


def test_sem_dupla_contagem_entre_provedor_de_dados_e_infraestrutura(db_session):
    _semear(db_session)
    lusha = next(c for c in MIG.COMPONENTES if c["servico"] == "SALES_INTELLIGENCE")
    with pytest.raises(ValidacaoFalhou, match="dupla contagem"):
        comissoes.infraestrutura.criar(db_session, {**{k: v for k, v in lusha.items() if k != "criado_por"},
                                                    "contabilizacao": "INFRASTRUCTURE"}, "teste")
    _envelope_neon(db_session)
    regras = dict(comissoes.politica.vigente_infra(db_session).regras, pools_comissao=["INFRASTRUCTURE"])
    comissoes.politica.nova_infra(db_session, regras, "Provedor de dados fora do cost-to-serve", "teste")
    assert comissoes.infraestrutura.pool(db_session, DIA)["por_pool"] == {"INFRASTRUCTURE": 10980.3}
    with pytest.raises(ValidacaoFalhou, match="AI_COST|pools_comissao"):
        comissoes.politica.nova_infra(db_session, dict(regras, pools_comissao=["AI_COST"]), "x", "teste")


def test_preco_custom_nunca_recebe_valor_publico_e_contrato_tem_prioridade(db_session):
    _semear(db_session)
    escala = next(c for c in MIG.COMPONENTES if c["servico"] == "SALES_INTELLIGENCE_SCALE")
    with pytest.raises(ValidacaoFalhou, match="CUSTOM"):
        comissoes.infraestrutura.criar(db_session, {**{k: v for k, v in escala.items() if k != "criado_por"}, "custo_referencia": 999.0,
                                                    "servico": "OUTRO"}, "teste")
    # contrato futuro do Lusha Scale substitui o preço público do mesmo serviço (não soma)
    premium = next(c for c in MIG.COMPONENTES if c["servico"] == "SALES_INTELLIGENCE")
    comissoes.infraestrutura.criar(db_session, {**{k: v for k, v in premium.items() if k != "criado_por"}, "plano": "Scale",
                                                "plano_referencia": "Scale", "custo_referencia": 800.0, "tipo_fonte": "CONTRACT"}, "teste")
    lushas = [c for c in comissoes.infraestrutura.aplicaveis(db_session, DIA, POOLS) if c.fornecedor == "LUSHA"]
    assert [(c.plano_referencia, c.tipo_fonte) for c in lushas] == [("Scale", "CONTRACT")]


def test_pesos_por_tier_incluindo_bid_intelligence_e_strategic_sourcing(db_session):
    _semear(db_session)
    _envelope_neon(db_session)
    for tenant_id, tier in (("t-start", "STARTER"), ("t-bid", "BID_INTELLIGENCE"), ("t-src", "STRATEGIC_SOURCING")):
        _tenant(db_session, tenant_id, tier)
    dados = comissoes.infraestrutura.pool(db_session, DIA)
    assert dados["unidades"] == 7 and dados["capacidade_nao_alocada"] == 0  # 1 + 2 + 4
    custos = {t: comissoes.infraestrutura.custo_tenant_mensal(dados, t)[0] for t in ("t-start", "t-bid", "t-src")}
    assert custos == {"t-start": Decimal("1854.26"), "t-bid": Decimal("3708.51"), "t-src": Decimal("7417.03")}  # 12.979,80 ÷ 7 × peso


def test_capacidade_nao_alocada_sem_tenants_e_com_capacidade_compartilhada(db_session):
    _semear(db_session)
    _envelope_neon(db_session)
    vazio = comissoes.infraestrutura.pool(db_session, DIA)
    assert (vazio["unidades"], vazio["alocado_tenants"], vazio["capacidade_nao_alocada"]) == (0, 0, Decimal("12979.80"))  # sem divisão por zero
    _tenant(db_session, "t-pro", "PROFESSIONAL")
    regras = dict(comissoes.politica.vigente_infra(db_session).regras, capacidade_unidades=20)
    comissoes.politica.nova_infra(db_session, regras, "Pool dimensionado para 20 unidades", "teste")
    dados = comissoes.infraestrutura.pool(db_session, DIA)
    assert (dados["alocado_tenants"], dados["capacidade_nao_alocada"]) == (Decimal("1297.98"), Decimal("11681.82"))  # 2/20 e 18/20
    assert comissoes.infraestrutura.custo_tenant_mensal(dados, "t-pro")[0] == Decimal("1297.98")
    resumo = comissoes.capacidade.economia_fornecedores(db_session, DIA)["resumo"]
    assert resumo["capacidade_nao_alocada_mensal"] == 11681.82


def test_comissao_historica_imutavel_quando_o_preco_muda(db_session):
    _semear(db_session)
    _envelope_neon(db_session)
    plano = _tenant(db_session, "t-pro", "PROFESSIONAL")
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": date(2000, 1, 1),
                                          "componentes": [{"tributo": "OTHER_TAX", "base": "RECEITA", "aliquota": 0.0}]}, "teste")
    rep = Representante(nome="R", email="r@forn.com", chave_pix="p", percentual_comissao=0.2)
    pagamento = PagamentoLicenca(tenant_id="t-pro", plano_id=plano.id, preferencia_id_externo="p1", status="aprovado", valor=20_000)
    db_session.add_all([rep, pagamento])
    db_session.flush()
    apuracao, (comissao,) = comissoes.motor.registrar_recebimento(
        db_session, origem=comissoes.tipos.Origem.PAGAMENTO_LICENCA, tenant_id="t-pro", segmento="PRIVATE", produto=plano.nome,
        tipo_receita="SAAS_SUBSCRIPTION", recebido_em=DIA, receita_bruta=20_000, beneficiarios=[(rep.id, 1)], taxa=0.2,
        pagamento_licenca_id=pagamento.id, meses_infra=1.0)
    db_session.commit()
    assert (comissao.status, apuracao.custo_infra, comissao.valor_comissao) == ("PAYABLE", Decimal("12979.80"), 1404.04)
    workspace = _componente(db_session, "RENDER", "WORKSPACE")
    comissoes.infraestrutura.atualizar(db_session, workspace.id, {"custo_referencia": 999, "verificado_em": DIA}, "Reajuste do Render", "teste")
    comissoes.motor.recalcular_nao_pagas(db_session, "Preço novo", "teste")
    db_session.refresh(comissao)
    db_session.refresh(apuracao)
    assert (comissao.valor_comissao, apuracao.custo_infra) == (1404.04, Decimal("12979.80"))  # snapshot preservado


def test_revisao_de_preco_vencida_aparece_nas_pendencias(client, db_session):
    _semear(db_session)
    workspace = _componente(db_session, "RENDER", "WORKSPACE")
    workspace.proxima_revisao_em = date.today() - timedelta(days=1)
    db_session.commit()
    pendentes = client.get("/api/v1/comissoes/parametros").json()["pendentes"]
    assert any(p.startswith("Revisar preço: RENDER · WORKSPACE") for p in pendentes)
    assert "Confirmar uso na arquitetura: RENDER · WEB_SERVICE_COMPUTE" in pendentes
    assert "Capacity envelope: NEON · POSTGRES" in pendentes
    assert not any("LUSHA" in p and "Valor" in p for p in pendentes) and not any("Enterprise" in p for p in pendentes)
