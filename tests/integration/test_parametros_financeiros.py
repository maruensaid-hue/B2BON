"""D-075: OI-024 (entitlements Government), OI-026 (Tax Engine com os parâmetros iniciais do PO) e OI-018 (câmbio).

Os parâmetros tributários vêm da migração `a6c8e0f2b4d7` (a fonte de produção); aqui a vigência é aberta para os testes
não dependerem da data de execução. Custos de infraestrutura e presunções não informadas pelo PO são valores de teste.
"""

import importlib.util
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.comissoes import contract as comissoes
from app.contexts.finops import contract as finops
from app.contexts.governo import contract as governo
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.auditoria import AuditLog
from app.models.creditos_ia import ExecucaoIa
from app.services.errors import ValidacaoFalhou
from tests.integration.test_comissao_margem import _comissoes, _receber, professional  # noqa: F401
from tests.integration.test_governo import planos_gov  # noqa: F401

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mig_d075", RAIZ / "alembic/versions/a6c8e0f2b4d7_parametros_financeiros_entitlements_gov.py")
MIG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MIG)
SEMPRE = date(2000, 1, 1)
INFRA_TESTE = [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.05}]


def _perfis_do_po(db, presuncao_licenca=None, vigente_de=SEMPRE):
    """Perfis iniciais da migração. `presuncao_licenca` (teste) completa o único valor que falta à licença."""
    for tipo, codigo, presuncao, iss, _ in MIG.PERFIS:
        presuncao = presuncao_licenca if tipo == "LICENCA_SOFTWARE" and presuncao_licenca else presuncao
        comissoes.tributos.criar(db, {"regime": "LUCRO_PRESUMIDO", "vigente_de": vigente_de, "tipo_receita": tipo, "municipio": MIG.MUNICIPIO,
                                      "codigo_servico": codigo, "componentes": MIG._componentes(presuncao, iss), "fonte": MIG.FONTE}, "teste")
    db.commit()


def _apuracao(db, recebimento):
    return db.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()


# ---------------------------------------------------------------- OI-024


ESPERADO = {
    "Department": {"internal_users": 20, "administrative_units": 1, "storage_gb": 100, "operational_retention_months": 12, "crm": True,
                   "map": True, "predator": True, "bid_intelligence": True, "public_procurement": "BASIC", "business_network": True,
                   "corporate_brain": True, "api_access": False, "sso": False, "support_sla": "BUSINESS_HOURS_8X5", "onboarding": "STANDARD"},
    "Professional": {"internal_users": 50, "administrative_units": 5, "storage_gb": 500, "operational_retention_months": 24, "crm": True,
                     "map": True, "predator": True, "bid_intelligence": True, "public_procurement": "FULL", "business_network": True,
                     "corporate_brain": True, "api_access": True, "sso": "OPTIONAL", "support_sla": "PRIORITY_BUSINESS_HOURS_8X5",
                     "onboarding": "ADVANCED"},
    "Enterprise": {"internal_users": 100, "administrative_units": 20, "storage_gb": 2048, "operational_retention_months": 60, "crm": True,
                   "map": True, "predator": True, "bid_intelligence": True, "public_procurement": "FULL", "business_network": True,
                   "corporate_brain": True, "api_access": True, "sso": True, "support_sla": "CRITICAL_BUSINESS_HOURS_8X5",
                   "onboarding": "DEDICATED"},
}


def test_entitlements_government_do_po_no_catalogo_unico(client, db_session, planos_gov):  # noqa: F811
    publico = {o["nome"].split()[-1]: o for o in client.get("/api/v1/catalogo").json()["governo"]["planos"]}
    assert {tier: o["entitlements"] for tier, o in publico.items()} == ESPERADO
    assert [(o["licenca"], o["implantacao"], o["assinatura_anual"], o["contratacao_inicial"], o["creditos_ia_anuais"])
            for o in publico.values()] == [(72_000, 12_000, 24_000, 108_000, 300_000), (120_000, 20_000, 36_000, 176_000, 600_000),
                                           (180_000, 30_000, 54_000, 264_000, 1_200_000)]
    assert publico["Professional"]["recomendado"] is True
    # Usuários e módulos ficam onde a plataforma os aplica: assentos (max_usuarios) e acesso (modulos_contratados)
    professional_ = planos_gov["Professional"]
    assert professional_.max_usuarios == 50 and {"map", "predator", "crm", "bids", "procurement"} <= set(professional_.modulos_contratados)


def test_entitlements_invalidos_sao_recusados_e_mudanca_e_auditada(client, db_session, planos_gov):  # noqa: F811
    plano = planos_gov["Department"]
    base, originais = {"nome": plano.nome, "franquia_contas_mes": 0, "preco_mensal": 0}, dict(plano.entitlements)
    for errado in ({"usuarios": 10}, {"sso": "SIM"}, {"storage_gb": -1}, {"public_procurement": "PREMIUM"}):
        resposta = client.put(f"/api/v1/planos/{plano.id}", json={**base, "entitlements": {**originais, **errado}, "motivo": "teste"})
        assert resposta.status_code == 422, errado
    resposta = client.put(f"/api/v1/planos/{plano.id}", json={**base, "entitlements": {**originais, "storage_gb": 200},
                                                              "motivo": "Aditivo"})
    assert resposta.status_code == 200
    assert governo.ofertas.entitlements(db_session.get(type(plano), plano.id))["storage_gb"] == 200
    log = db_session.query(AuditLog).filter_by(evento_tipo="plano_alterado", entidade_id=plano.id).order_by(AuditLog.id.desc()).first()
    assert log.detalhes["mudancas"]["entitlements"]["depois"]["storage_gb"] == 200


# ---------------------------------------------------------------- OI-026: Tax Engine


def test_parametros_iniciais_do_po_por_tributo_sem_inventar_o_que_falta():
    perfis = {tipo: (codigo, MIG._componentes(presuncao, iss)) for tipo, codigo, presuncao, iss, _ in MIG.PERFIS}
    por_tributo = lambda tipo: {c["tributo"]: c for c in perfis[tipo][1]}  # noqa: E731
    for tipo in perfis:
        t = por_tributo(tipo)
        assert (t["PIS"]["aliquota"], t["COFINS"]["aliquota"], t["IRPJ"]["aliquota"], t["CSLL"]["aliquota"]) == (0.0065, 0.03, 0.15, 0.09)
        assert (t["CBS"]["aliquota_teste"], t["IBS"]["aliquota_teste"]) == (0.009, 0.001)
        assert t["CBS"]["aliquota_caixa_efetiva"] is None and t["IBS"]["aliquota_caixa_efetiva"] is None
        assert "IRPJ_ADDITIONAL" not in t
    assert perfis["LICENCA_SOFTWARE"][0] == "1.05" and por_tributo("LICENCA_SOFTWARE")["ISS"]["aliquota"] == 0.029
    assert por_tributo("SERVICO")["IRPJ"]["presuncao"] == 0.32 and por_tributo("SERVICO")["ISS"]["aliquota"] is None
    assert por_tributo("LICENCA_SOFTWARE")["IRPJ"]["presuncao"] is None and por_tributo("SAAS")["CSLL"]["presuncao"] is None
    assert por_tributo("SAAS")["ISS"]["aliquota"] is None  # 2,90% é de São Paulo para o item 1.05, não nacional
    assert (MIG.MUNICIPIO, MIG.VIGENCIA) == ("São Paulo/SP", (date(2026, 1, 1), date(2027, 1, 1)))


def test_irpj_e_csll_por_presuncao_iss_de_sao_paulo_e_cbs_ibs_teste_fora_da_carga(db_session, professional):  # noqa: F811
    _perfis_do_po(db_session, presuncao_licenca=0.32)  # presunção da licença: valor de teste (o PO ainda não informou)
    comissoes.infraestrutura.criar(db_session, {"nome": "Infra teste", "vigente_de": SEMPRE, "componentes": INFRA_TESTE}, "teste")
    db_session.commit()
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 120_000))
    linhas = {linha["tributo"]: linha for linha in apuracao.detalhe["tributos"]["tributos"]}
    # PIS 780 + COFINS 3.600 + ISS 3.480 + IRPJ (120.000 × 32% × 15%) 5.760 + CSLL (120.000 × 32% × 9%) 3.456
    assert {t: linhas[t]["valor"] for t in ("PIS", "COFINS", "ISS", "IRPJ", "CSLL")} == {
        "PIS": 780.0, "COFINS": 3600.0, "ISS": 3480.0, "IRPJ": 5760.0, "CSLL": 3456.0}
    assert linhas["IRPJ"]["base"] == 38_400.0  # base presumida, não a receita
    assert (linhas["CBS"]["valor_teste"], linhas["CBS"]["valor"], linhas["IBS"]["valor_teste"], linhas["IBS"]["valor"]) == (1080.0, 0.0, 120.0, 0.0)
    assert apuracao.impostos == Decimal("17076.00")  # sem somar 1% de CBS/IBS-teste
    assert apuracao.aliquota_tributaria == pytest.approx(0.1423)
    assert apuracao.margem_comissionavel_liquida == Decimal("96924.00")  # 120.000 − 17.076 − 6.000 (infra de teste)
    assert _comissoes(db_session)[0].valor_comissao == 19_384.8  # 20% da margem, nunca 20% de 120.000


def test_cbs_ibs_so_entram_pelo_caixa_efetivo_e_nunca_se_compensados(db_session, professional):  # noqa: F811
    base = [{"tributo": "PIS", "base": "RECEITA", "aliquota": 0.0065}]
    cbs = {"tributo": "CBS", "base": "TESTE_REFORMA", "aliquota_teste": 0.009, "aliquota_caixa_efetiva": 0.009, "compensado": False,
           "dispensado": False, "status_conformidade": "PENDENTE"}
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE, "componentes": [*base, cbs]}, "teste")
    comissoes.infraestrutura.criar(db_session, {"nome": "Infra", "vigente_de": SEMPRE, "componentes": INFRA_TESTE}, "teste")
    db_session.commit()
    assert _apuracao(db_session, _receber(db_session, professional, "LICENSE", 60_000)).impostos == Decimal("930.00")  # 390 + 540
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": date(2001, 1, 1),
                                          "componentes": [*base, {**cbs, "compensado": True}]}, "teste")
    db_session.commit()
    assert _apuracao(db_session, _receber(db_session, professional, "LICENSE", 60_000)).impostos == Decimal("390.00")


def test_adicional_de_irpj_so_sobre_a_base_presumida_acima_do_limite_do_periodo(db_session, professional):  # noqa: F811
    componentes = [{"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": 0.32},
                   {"tributo": "IRPJ_ADDITIONAL", "base": "PRESUNCAO_EXCEDENTE", "aliquota": 0.10, "presuncao": 0.32,
                    "limite_periodo": 30_000, "periodo": "TRIMESTRAL"}]  # valores de teste
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE, "componentes": componentes}, "teste")
    comissoes.infraestrutura.criar(db_session, {"nome": "Infra", "vigente_de": SEMPRE, "componentes": INFRA_TESTE}, "teste")
    db_session.commit()
    dia = date.today()
    primeira = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 80_000, dia))  # base 25.600 < 30.000
    segunda = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 40_000, dia))  # base 12.800: acumulado 38.400
    adicional = lambda a: next(t for t in a.detalhe["tributos"]["tributos"] if t["tributo"] == "IRPJ_ADDITIONAL")  # noqa: E731
    assert (adicional(primeira)["valor"], adicional(segunda)["valor"], adicional(segunda)["base"]) == (0.0, 840.0, 8400.0)


def test_perfil_do_po_sem_presuncao_aguarda_com_simulacao_e_infra_tem_prioridade_no_status(client, db_session, professional):  # noqa: F811
    _perfis_do_po(db_session)
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 120_000))
    assert apuracao.parametros_faltantes == ["TAX_PROFILE", "INFRASTRUCTURE_COST"]
    assert apuracao.detalhe["tributos"]["pendencias"] == ["IRPJ: percentual de presunção para LICENCA_SOFTWARE",
                                                          "CSLL: percentual de presunção para LICENCA_SOFTWARE"]
    assert apuracao.detalhe["tributos"]["simulacao_parcial"] == 7860.0  # PIS + COFINS + ISS já calculados
    dados = client.get("/api/v1/comissoes/apuracoes").json()[0]
    assert dados["commission_amount_status"] == "AWAITING_INFRASTRUCTURE_COST" and dados["net_commissionable_margin"] is None
    pendentes = client.get("/api/v1/comissoes/parametros").json()["pendentes"]
    assert "Infrastructure Cost Model (custos reais de infraestrutura)" in pendentes
    assert "Tax Profile LICENCA_SOFTWARE: IRPJ: presunção" in pendentes and "Tax Profile SAAS: ISS: alíquota" in pendentes
    assert "Tax Profile SERVICO: ISS: alíquota" in pendentes and not any("SERVICO: IRPJ" in p for p in pendentes)


def test_implantacao_tem_impostos_simulados_e_continua_sem_comissao(db_session, professional):  # noqa: F811
    _perfis_do_po(db_session)
    apuracao = _apuracao(db_session, _receber(db_session, professional, "IMPLEMENTATION", 20_000))
    linhas = {t["tributo"]: t["valor"] for t in apuracao.detalhe["tributos"]["tributos"]}
    assert (linhas["IRPJ"], linhas["CSLL"], linhas["ISS"]) == (960.0, 576.0, None)  # presunção de 32% de serviços
    assert _comissoes(db_session) == []


def test_validacao_do_tax_profile(db_session):
    def criar(componentes):
        comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE, "componentes": componentes}, "teste")
    for errado in ([{"tributo": "IPI", "aliquota": 0.1}], [{"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15}],
                   [{"tributo": "PIS", "aliquota": 1.2}], [{"tributo": "ISS", "base": "TESTE_REFORMA", "aliquota_teste": 0.01}],
                   [{"tributo": "PIS", "aliquota": 0.01}, {"tributo": "PIS", "aliquota": 0.01}]):
        with pytest.raises(ValidacaoFalhou):
            criar(errado)


# ---------------------------------------------------------------- Infrastructure Cost Model


def test_metodos_de_infraestrutura_por_categoria(db_session, professional, criar_usuario_autenticado):  # noqa: F811
    from tests.parametros_comissao import definir_parametros

    componentes = [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.02},
                   {"categoria": "database_cost", "metodo": "FIXED", "valor": 150},
                   {"categoria": "storage_cost", "metodo": "PER_TENANT", "valores": {professional.tenant_id: 300}, "padrao": 50},
                   {"categoria": "observability_cost", "metodo": "PER_USER", "valor_por_usuario": 10}]
    criar_usuario_autenticado(email="u1@orgao.gov", papel="admin", tenant_id=professional.tenant_id)
    definir_parametros(db_session, infra=componentes)
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 100_000))
    assert apuracao.custo_infra == Decimal("2460.00")  # 2.000 + 150 + 300 + 10 × 1 usuário
    assert db_session.get(type(apuracao.modelo_custo_infra_id and comissoes.infraestrutura.aplicavel(db_session, date.today())),
                          apuracao.modelo_custo_infra_id).metodo == "HYBRID"
    with pytest.raises(ValidacaoFalhou, match="USAGE_BASED"):
        comissoes.infraestrutura.criar(db_session, {"nome": "x", "vigente_de": date.today() + timedelta(days=1),
                                                    "componentes": [{"categoria": "cloud_cost", "metodo": "USAGE_BASED"}]}, "teste")
    with pytest.raises(ValidacaoFalhou):
        comissoes.infraestrutura.criar(db_session, {"nome": "x", "vigente_de": date.today() + timedelta(days=1),
                                                    "componentes": [{"categoria": "energia", "metodo": "FIXED", "valor": 1}]}, "teste")


# ---------------------------------------------------------------- OI-018: câmbio


def _execucao_ia(db, tenant_id, usd, quando):
    db.add(ExecucaoIa(id=str(uuid.uuid4()), tenant_id=tenant_id, idempotency_key=str(uuid.uuid4()), workload_codigo="w", catalogo_versao="1",
                      classe="c", modulo="crm", status="LIQUIDADA", custo_total_usd=usd, custo_total_brl=None, criado_em=quando))
    db.commit()


def test_cotacao_aplicavel_por_vigencia_sem_valor_no_codigo(db_session):
    assert finops.comercial.cambio_usd_brl(db_session) is None
    finops.cambio.registrar(db_session, {"moeda_base": "usd", "moeda_cotacao": "brl", "taxa": 5.0, "fonte": "PTAX teste",
                                         "vigente_em": datetime(2026, 1, 1)}, "teste")
    finops.cambio.registrar(db_session, {"moeda_base": "USD", "moeda_cotacao": "BRL", "taxa": 5.5, "fonte": "PTAX teste",
                                         "vigente_em": datetime(2026, 6, 1)}, "teste")
    assert finops.comercial.cambio_usd_brl(db_session, datetime(2026, 3, 1)) == Decimal("5.0")
    assert finops.comercial.cambio_usd_brl(db_session, datetime(2026, 7, 1)) == Decimal("5.5")
    assert finops.comercial.cambio_usd_brl(db_session, datetime(2025, 12, 31)) is None
    with pytest.raises(ValidacaoFalhou):
        finops.cambio.registrar(db_session, {"moeda_base": "USD", "moeda_cotacao": "BRL", "taxa": 5.0, "fonte": " "}, "teste")


def test_custo_de_ia_em_usd_aguarda_cotacao_e_converte_quando_informada(client, db_session, professional):  # noqa: F811
    from tests.parametros_comissao import definir_parametros

    definir_parametros(db_session, impostos=0.10, infra=INFRA_TESTE)
    resposta = client.post("/api/v1/comissoes/politica-margem", json={"deduzir_custo_ia": True, "motivo": "PO: IA na margem"})
    assert resposta.status_code == 201 and resposta.json()["versao"] == 2
    _execucao_ia(db_session, professional.tenant_id, 100, datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=1))
    recebimento = _receber(db_session, professional, "LICENSE", 100_000)
    dados = next(a for a in client.get("/api/v1/comissoes/apuracoes").json() if a["id"] == _apuracao(db_session, recebimento).id)
    assert dados["missing_parameters"] == ["FX_RATE"] and dados["commission_amount_status"] == "AWAITING_FX_RATE"
    resposta = client.post("/api/v1/comissoes/cotacoes-cambio", json={"taxa": 5.25, "fonte": "PTAX teste",
                                                                      "vigente_em": f"{date.today() - timedelta(days=40)}T00:00:00"})
    assert resposta.status_code == 201 and resposta.json()["aguardando_calculadas"] == 1
    apuracao = _apuracao(db_session, recebimento)
    db_session.refresh(apuracao)
    # 100.000 − 10.000 − (5.000 de infra + 100 USD × 5,25 = 525 de IA)
    assert (apuracao.custo_ia, apuracao.margem_comissionavel_liquida) == (Decimal("525.00"), Decimal("84475.00"))
    assert db_session.query(AuditLog).filter_by(evento_tipo="cotacao_cambio_registrada").count() == 1


def test_politica_da_margem_so_define_custo_de_ia_e_exige_motivo(client):
    assert client.post("/api/v1/comissoes/politica-margem", json={"deduzir_custo_ia": True, "motivo": ""}).status_code == 422
    with pytest.raises(ValidacaoFalhou):
        comissoes.politica.nova(None, {"deduzir_custo_ia": True, "deduzir_impostos": False}, "tirar impostos", "teste")
    assert client.get("/api/v1/comissoes/parametros").json()["politica_margem"] == {"versao": 1, "regras": {"deduzir_custo_ia": False}}


def test_waterfall_mostra_impostos_por_tributo_e_pendencias_por_parametro(client, db_session, professional):  # noqa: F811
    _perfis_do_po(db_session, presuncao_licenca=0.32)
    _receber(db_session, professional, "LICENSE", 120_000)  # sem infraestrutura: aguarda
    comissoes.infraestrutura.criar(db_session, {"nome": "Infra", "vigente_de": SEMPRE, "componentes": INFRA_TESTE}, "teste")
    comissoes.motor.recalcular_aguardando(db_session)
    db_session.commit()
    _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000)  # SaaS: presunção e ISS pendentes
    total = client.get("/api/v1/comissoes/waterfall").json()["total"]
    assert total["impostos_por_tributo"] == {"CBS": 0.0, "COFINS": 3600.0, "CSLL": 3456.0, "IBS": 0.0, "IRPJ": 5760.0, "ISS": 3480.0,
                                             "PIS": 780.0}
    assert total["aguardando_por_parametro"] == {"AWAITING_TAX_PROFILE": 1} and total["impostos"] == 17_076.0
