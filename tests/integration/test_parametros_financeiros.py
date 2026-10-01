"""D-075/D-076: entitlements Government (OI-024), Tax Engine com os parâmetros do PO (OI-026) e câmbio PTAX (OI-018).

Os perfis tributários vêm da migração `b7d9f1a3c5e8` (a fonte de produção); aqui a vigência é aberta para os testes não
dependerem da data de execução. Custos de infraestrutura e limites marcados "de teste" não são do PO.
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
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider
from app.services.errors import ValidacaoFalhou
from tests.integration.test_comissao_margem import _comissoes, _receber, professional  # noqa: F401
from tests.integration.test_governo import MIG as MIG_D072
from tests.integration.test_governo import planos_gov  # noqa: F401
from tests.parametros_comissao import componente, definir_parametros

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mig_d076", RAIZ / "alembic/versions/b7d9f1a3c5e8_pool_infraestrutura_tributos_2026.py")
MIG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MIG)
SEMPRE = date(2000, 1, 1)


def _perfis_do_po(db, vigente_de=SEMPRE):
    for tipo, item, codigo, presuncao, iss, _ in MIG.PERFIS:
        comissoes.tributos.criar(db, {"regime": "LUCRO_PRESUMIDO", "vigente_de": vigente_de, "tipo_receita": tipo, "municipio": MIG.MUNICIPIO,
                                      "item_lista_servico": item, "codigo_servico": codigo, "versao_legal": MIG.VERSAO_LEGAL,
                                      "componentes": MIG.componentes(presuncao, iss), "fonte": MIG.FONTE}, "teste")
    db.commit()


def _pool_zero(db):
    comissoes.infraestrutura.criar(db, componente(0.0), "teste")
    db.commit()


def _apuracao(db, recebimento):
    return db.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()


def _linhas(apuracao):
    return {linha["tributo"]: linha for linha in apuracao.detalhe["tributos"]["tributos"]}


# ---------------------------------------------------------------- OI-024


ESPERADO = {
    "Department": {"internal_users": 20, "administrative_units": 1, "monthly_accounts": 1_000, "ai_credits_annual": 300_000, "storage_gb": 100,
                   "operational_retention_months": 12, "crm": True, "map": True, "predator": True, "bid_intelligence": True,
                   "public_procurement": "BASIC", "business_network": True, "corporate_brain": True, "api_access": False, "sso": False,
                   "support_sla": "BUSINESS_HOURS_8X5", "onboarding": "STANDARD"},
    "Professional": {"internal_users": 50, "administrative_units": 5, "monthly_accounts": 3_000, "ai_credits_annual": 600_000,
                     "storage_gb": 500, "operational_retention_months": 24, "crm": True, "map": True, "predator": True,
                     "bid_intelligence": True, "public_procurement": "FULL", "business_network": True, "corporate_brain": True,
                     "api_access": True, "sso": "OPTIONAL", "support_sla": "PRIORITY_BUSINESS_HOURS_8X5", "onboarding": "ADVANCED"},
    "Enterprise": {"internal_users": 100, "administrative_units": 20, "monthly_accounts": 10_000, "ai_credits_annual": 1_200_000,
                   "storage_gb": 2048, "operational_retention_months": 60, "crm": True, "map": True, "predator": True,
                   "bid_intelligence": True, "public_procurement": "FULL", "business_network": True, "corporate_brain": True,
                   "api_access": True, "sso": True, "support_sla": "CRITICAL_BUSINESS_HOURS_8X5", "onboarding": "DEDICATED"},
}


def test_entitlements_government_do_po_no_catalogo_unico(client, db_session, planos_gov):  # noqa: F811
    publico = {o["nome"].split()[-1]: o for o in client.get("/api/v1/catalogo").json()["governo"]["planos"]}
    assert {tier: o["entitlements"] for tier, o in publico.items()} == ESPERADO
    assert [(o["licenca"], o["implantacao"], o["assinatura_anual"], o["contratacao_inicial"], o["creditos_ia_anuais"])
            for o in publico.values()] == [(72_000, 12_000, 24_000, 108_000, 300_000), (120_000, 20_000, 36_000, 176_000, 600_000),
                                           (180_000, 30_000, 54_000, 264_000, 1_200_000)]
    assert publico["Professional"]["recomendado"] is True
    assert "supplier_360" not in publico["Department"]["capacidades_public_procurement"]
    assert {"demand_management", "audit_trail"} <= set(publico["Department"]["capacidades_public_procurement"])
    assert {"supplier_360", "risk_engine", "apis_integrations"} <= set(publico["Professional"]["capacidades_public_procurement"])
    professional_ = planos_gov["Professional"]
    assert professional_.max_usuarios == 50 and {"map", "predator", "crm", "bids", "procurement"} <= set(professional_.modulos_contratados)


def test_franquia_mensal_de_contas_separada_dos_ai_credits(db_session, planos_gov):  # noqa: F811
    for tier, contas in (("Department", 1_000), ("Professional", 3_000), ("Enterprise", 10_000)):
        tenant_id = f"gov-{tier.lower()}"
        db_session.add_all([Tenant(id=tenant_id, razao_social=tier), Licenca(tenant_id=tenant_id, plano_id=planos_gov[tier].id, status="ativa")])
        db_session.commit()
        limites = NucleoPlanLimitsProvider(db_session)
        assert limites.obter_franquia_contas_mes(tenant_id) == contas  # MAP/PREDATOR funcionam dentro da franquia
        assert planos_gov[tier].creditos_ia_anuais != contas


def test_public_procurement_basic_e_full_no_mesmo_motor(client, db_session, planos_gov, criar_usuario_autenticado):  # noqa: F811
    from app.api.deps import get_plan_limits_provider
    from app.main import app

    app.dependency_overrides[get_plan_limits_provider] = lambda: NucleoPlanLimitsProvider(db_session)  # o plano real decide
    cabecalhos = {}
    for tier in ("Department", "Professional"):
        tenant_id = f"compras-{tier.lower()}"
        db_session.add_all([Tenant(id=tenant_id, razao_social=tier), Licenca(tenant_id=tenant_id, plano_id=planos_gov[tier].id, status="ativa")])
        db_session.commit()
        cabecalhos[tier] = criar_usuario_autenticado(tenant_id)
    for rota in ("/api/v1/procurement/metricas", "/api/v1/procurement/demandas"):
        assert client.get(rota, headers=cabecalhos["Department"]).status_code == 200  # BASIC
    for rota in ("/api/v1/procurement/riscos", "/api/v1/procurement/proximas-acoes"):
        assert client.get(rota, headers=cabecalhos["Department"]).status_code == 403, rota  # FULL
        assert client.get(rota, headers=cabecalhos["Professional"]).status_code == 200, rota


def test_entitlements_invalidos_sao_recusados_e_mudanca_e_auditada(client, db_session, planos_gov):  # noqa: F811
    plano = planos_gov["Department"]
    base, originais = {"nome": plano.nome, "franquia_contas_mes": 1_000, "preco_mensal": 0}, dict(plano.entitlements)
    for errado in ({"usuarios": 10}, {"sso": "SIM"}, {"storage_gb": -1}, {"public_procurement": "PREMIUM"}):
        resposta = client.put(f"/api/v1/planos/{plano.id}", json={**base, "entitlements": {**originais, **errado}, "motivo": "teste"})
        assert resposta.status_code == 422, errado
    resposta = client.put(f"/api/v1/planos/{plano.id}", json={**base, "entitlements": {**originais, "storage_gb": 200},
                                                              "motivo": "Aditivo"})
    assert resposta.status_code == 200
    assert governo.ofertas.entitlements(db_session.get(Plano, plano.id))["storage_gb"] == 200
    log = db_session.query(AuditLog).filter_by(evento_tipo="plano_alterado", entidade_id=plano.id).order_by(AuditLog.id.desc()).first()
    assert log.detalhes["mudancas"]["entitlements"]["depois"]["storage_gb"] == 200


# ---------------------------------------------------------------- OI-026: Tax Engine


def test_parametros_tributarios_do_po_sem_inventar_o_que_falta():
    perfis = {tipo: (item, codigo, MIG.componentes(presuncao, iss)) for tipo, item, codigo, presuncao, iss, _ in MIG.PERFIS}
    assert set(perfis) == {"SOFTWARE_LICENSE", "SAAS_SUBSCRIPTION", "IMPLEMENTATION"}  # consultoria e suporte: sem perfil
    for tipo, (_, _, componentes_) in perfis.items():
        t = {c["tributo"]: c for c in componentes_}
        assert (t["PIS"]["aliquota"], t["COFINS"]["aliquota"]) == (0.0065, 0.03)
        assert (t["IRPJ"]["aliquota"], t["IRPJ"]["presuncao"], t["CSLL"]["aliquota"], t["CSLL"]["presuncao"]) == (0.15, 0.32, 0.09, 0.32)
        assert t["IRPJ"]["acrescimo_presuncao"] == {"percentual": 0.10, "limite_anual": 5_000_000, "periodo": "TRIMESTRAL"}
        assert (t["IRPJ_ADDITIONAL"]["aliquota"], t["IRPJ_ADDITIONAL"]["limite_mensal"], t["IRPJ_ADDITIONAL"]["periodo"]) == (
            0.10, 20_000, "TRIMESTRAL")
        assert (t["CBS"]["aliquota_teste"], t["IBS"]["aliquota_teste"]) == (0.009, 0.001)
        assert t["CBS"]["situacao"] == t["IBS"]["situacao"] == "PENDING_COMPLIANCE_CONFIRMATION"
    assert perfis["SOFTWARE_LICENSE"][:2] == ("1.05", "2800") and {c["tributo"]: c for c in perfis["SOFTWARE_LICENSE"][2]}["ISS"]["aliquota"] == 0.029
    assert perfis["IMPLEMENTATION"][:2] == ("1.07", "2919") and {c["tributo"]: c for c in perfis["IMPLEMENTATION"][2]}["ISS"]["aliquota"] == 0.029
    assert perfis["SAAS_SUBSCRIPTION"][:2] == (None, None) and {c["tributo"]: c for c in perfis["SAAS_SUBSCRIPTION"][2]}["ISS"]["aliquota"] is None
    assert (MIG.MUNICIPIO, MIG.VIGENCIA) == ("São Paulo/SP", (date(2026, 1, 1), date(2027, 1, 1)))  # 2027+: perfil novo, nunca estendido


def test_licenca_de_software_presuncao_e_base_nao_imposto_iss_sp_e_cbs_ibs_fora_da_carga(db_session, professional):  # noqa: F811
    _perfis_do_po(db_session)
    _pool_zero(db_session)
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 120_000))
    linhas = _linhas(apuracao)
    # PIS 780 + COFINS 3.600 + ISS 3.480 + IRPJ (120.000 × 32% = 38.400 × 15%) 5.760 + CSLL (38.400 × 9%) 3.456
    assert {t: linhas[t]["valor"] for t in ("PIS", "COFINS", "ISS", "IRPJ", "CSLL", "IRPJ_ADDITIONAL")} == {
        "PIS": 780.0, "COFINS": 3600.0, "ISS": 3480.0, "IRPJ": 5760.0, "CSLL": 3456.0, "IRPJ_ADDITIONAL": 0.0}
    assert linhas["IRPJ"]["base"] == 38_400.0  # 32% é a base presumida, não imposto
    assert (linhas["CBS"]["valor_teste"], linhas["CBS"]["valor"], linhas["IBS"]["valor"]) == (1080.0, 0.0, 0.0)
    assert apuracao.impostos == Decimal("17076.00") and apuracao.margem_comissionavel_liquida == Decimal("102924.00")
    assert (apuracao.detalhe["tributos"]["item_lista_servico"], apuracao.detalhe["tributos"]["codigo_servico"]) == ("1.05", "2800")
    assert _comissoes(db_session)[0].valor_comissao == 20_584.8  # 20% da margem, nunca 20% de 120.000


def test_adicional_de_irpj_acima_de_20_mil_por_mes_do_trimestre(db_session):
    """Enterprise: licença 180.000 (base 57.600) e implantação 30.000 (base 9.600) no mesmo trimestre → base acumulada 67.200,
    limite 60.000 (R$ 20.000 × 3): adicional de 10% só sobre os 7.200 excedentes = 720."""
    _perfis_do_po(db_session)
    _pool_zero(db_session)
    nome, licenca, implantacao, assinatura, creditos, recomendado = MIG_D072.PLANOS[2]
    plano = Plano(nome=nome, franquia_contas_mes=10_000, preco_mensal=0.0, visivel_self_service=False, modulos_contratados=["procurement"],
                  categoria="governo", tipo_preco="CONTRACT", segmento="GOVERNMENT", modelo_cobranca=MIG_D072.MODELO, preco_licenca=licenca,
                  preco_implantacao=implantacao, preco_assinatura_anual=assinatura, creditos_ia_anuais=creditos, tier_infraestrutura="ENTERPRISE")
    db_session.add_all([plano, Tenant(id="orgao-ent", razao_social="Órgão")])
    db_session.commit()
    contrato = governo.contratos.criar(db_session, tenant_id="orgao-ent", plano_id=plano.id, modelo=MIG_D072.MODELO, referencia_contrato="CT-E",
                                       entidade_governamental="Órgão", assinado_em=date.today() - timedelta(days=10))
    primeira = _apuracao(db_session, _receber(db_session, contrato, "LICENSE", 180_000))
    segunda = _apuracao(db_session, _receber(db_session, contrato, "IMPLEMENTATION", 30_000))
    assert _linhas(primeira)["IRPJ_ADDITIONAL"]["valor"] == 0.0
    adicional = _linhas(segunda)["IRPJ_ADDITIONAL"]
    assert (adicional["base"], adicional["limite_periodo"], adicional["valor"]) == (7_200.0, 60_000.0, 720.0)
    assert segunda.tipo_receita == "IMPLEMENTATION" and segunda.detalhe["tributos"]["codigo_servico"] == "2919"


def test_acrescimo_de_presuncao_2026_so_na_receita_acima_do_limite(db_session, professional):  # noqa: F811
    """Regra versionada: presunção × 1,10 na parcela acima do limite do período (limite de teste: 400.000/ano = 100.000/tri)."""
    irpj = {"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": 0.32,
            "acrescimo_presuncao": {"percentual": 0.10, "limite_anual": 400_000, "periodo": "TRIMESTRAL"}}
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE, "componentes": [irpj]}, "teste")
    _pool_zero(db_session)
    primeira = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 80_000))
    segunda = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 40_000))
    assert _linhas(primeira)["IRPJ"]["base"] == 25_600.0
    # 20.000 até o limite × 32% + 20.000 acima × 35,2% = 6.400 + 7.040 = 13.440 → IRPJ 2.016 (não 32% + 10 pontos)
    assert (_linhas(segunda)["IRPJ"]["base"], _linhas(segunda)["IRPJ"]["valor"], _linhas(segunda)["IRPJ"]["presuncao_acrescida"]) == (
        13_440.0, 2_016.0, pytest.approx(0.352))


def test_cbs_ibs_so_entram_quando_devidos(db_session, professional):  # noqa: F811
    base = [{"tributo": "PIS", "base": "RECEITA", "aliquota": 0.0065}]
    cbs = {"tributo": "CBS", "base": "TESTE_REFORMA", "aliquota_teste": 0.009, "situacao": "PAYABLE"}
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE, "componentes": [*base, cbs]}, "teste")
    _pool_zero(db_session)
    assert _apuracao(db_session, _receber(db_session, professional, "LICENSE", 60_000)).impostos == Decimal("930.00")  # 390 + 540
    for situacao in ("COMPENSATED", "WAIVED_BY_COMPLIANCE", "PENDING_COMPLIANCE_CONFIRMATION"):
        comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE + timedelta(days=len(situacao)),
                                              "componentes": [*base, {**cbs, "situacao": situacao}]}, "teste")
        db_session.commit()
        assert _apuracao(db_session, _receber(db_session, professional, "LICENSE", 20_000)).impostos == Decimal("130.00"), situacao


def test_saas_sem_iss_aguarda_com_simulacao_e_infra_tem_prioridade_no_status(client, db_session, professional):  # noqa: F811
    _perfis_do_po(db_session)
    apuracao = _apuracao(db_session, _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000))
    assert apuracao.tipo_receita == "SAAS_SUBSCRIPTION" and apuracao.parametros_faltantes == ["TAX_PROFILE", "INFRASTRUCTURE_COST"]
    assert apuracao.detalhe["tributos"]["pendencias"] == ["ISS: alíquota"]
    assert apuracao.detalhe["tributos"]["simulacao_parcial"] == 4_078.8  # PIS 234 + COFINS 1.080 + IRPJ 1.728 + CSLL 1.036,80
    dados = client.get("/api/v1/comissoes/apuracoes").json()[0]
    assert dados["commission_amount_status"] == "AWAITING_INFRASTRUCTURE_COST" and dados["net_commissionable_margin"] is None
    pendentes = client.get("/api/v1/comissoes/parametros").json()["pendentes"]
    assert "Infrastructure Cost Pool: fornecedores e planos de referência com valores" in pendentes
    assert "Tax Profile SAAS_SUBSCRIPTION: ISS: alíquota" in pendentes
    assert {"Tax Profile vigente para CONSULTING", "Tax Profile vigente para SUPPORT"} <= set(pendentes)
    assert not any("SOFTWARE_LICENSE" in p or "IMPLEMENTATION" in p for p in pendentes)


def test_servico_adicional_sem_classificacao_aguarda_e_classificado_usa_o_perfil(db_session, professional):  # noqa: F811
    _perfis_do_po(db_session)
    _pool_zero(db_session)
    sem = governo.contratos.adicionar_componente(db_session, professional.id, tipo="ADDITIONAL_SERVICES", valor=10_000, descricao="Treinamento")
    apuracao = _apuracao(db_session, governo.recebimentos.registrar(db_session, professional.id, componente_id=sem.id, valor=10_000,
                                                                    recebido_em=date.today()))
    assert apuracao.tipo_receita == "UNCLASSIFIED" and apuracao.parametros_faltantes == ["TAX_PROFILE"]
    com = governo.contratos.adicionar_componente(db_session, professional.id, tipo="ADDITIONAL_SERVICES", valor=10_000,
                                                 descricao="Configuração", tipo_receita="IMPLEMENTATION")
    apuracao = _apuracao(db_session, governo.recebimentos.registrar(db_session, professional.id, componente_id=com.id, valor=10_000,
                                                                    recebido_em=date.today()))
    assert apuracao.tipo_receita == "IMPLEMENTATION" and apuracao.status == "CALCULATED"
    with pytest.raises(ValidacaoFalhou):
        governo.contratos.adicionar_componente(db_session, professional.id, tipo="ADDITIONAL_SERVICES", valor=1, tipo_receita="SERVICO")


def test_validacao_do_tax_profile(db_session):
    def criar(componentes_):
        comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": SEMPRE, "componentes": componentes_}, "teste")
    for errado in ([{"tributo": "IPI", "aliquota": 0.1}], [{"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15}],
                   [{"tributo": "PIS", "aliquota": 1.2}], [{"tributo": "ISS", "base": "TESTE_REFORMA", "aliquota_teste": 0.01}],
                   [{"tributo": "CBS", "base": "TESTE_REFORMA", "aliquota_teste": 0.009, "situacao": "TALVEZ"}],
                   [{"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": 0.32, "acrescimo_presuncao": {"percentual": 0.1}}],
                   [{"tributo": "PIS", "aliquota": 0.01}, {"tributo": "PIS", "aliquota": 0.01}]):
        with pytest.raises(ValidacaoFalhou):
            criar(errado)


# ---------------------------------------------------------------- OI-018: câmbio PTAX


def _execucao_ia(db, tenant_id, usd, quando):
    db.add(ExecucaoIa(id=str(uuid.uuid4()), tenant_id=tenant_id, idempotency_key=str(uuid.uuid4()), workload_codigo="w", catalogo_versao="1",
                      classe="c", modulo="crm", status="LIQUIDADA", custo_total_usd=usd, custo_total_brl=None, criado_em=quando))
    db.commit()


def test_ptax_de_fechamento_do_banco_central_sem_valor_no_codigo(db_session):
    assert finops.comercial.cambio_usd_brl(db_session) is None
    consultas = []

    def buscar(dia):
        consultas.append(dia)
        return None if dia == date(2026, 9, 29) else Decimal("5.40") + Decimal(dia.day) / 100

    resultado = finops.cambio.sincronizar_ptax(db_session, hoje=date(2026, 9, 30), buscar=buscar)
    assert all(dia.weekday() < 5 for dia in consultas)  # só dias úteis
    assert "2026-09-29" not in resultado["gravadas"] and "2026-09-30" in resultado["gravadas"]
    # sem PTAX no dia 29: vale a última anterior (dia 28)
    linha = finops.cambio.aplicavel(db_session, "USD", "BRL", datetime(2026, 9, 29, 18))
    assert (linha.data_cotacao, linha.tipo, linha.fonte, float(linha.taxa)) == (date(2026, 9, 28), "PTAX_CLOSE", "BANCO_CENTRAL_DO_BRASIL", 5.68)
    assert set(finops.cambio.snapshot(linha)) >= {"fx_rate", "fx_date", "source", "retrieved_at"}
    assert finops.cambio.sincronizar_ptax(db_session, hoje=date(2026, 9, 30), buscar=buscar)["gravadas"] == ["2026-09-29"][:0]  # idempotente
    falha = finops.cambio.sincronizar_ptax(db_session, hoje=date(2026, 10, 2), buscar=lambda dia: (_ for _ in ()).throw(OSError("rede")))
    assert falha["erro"] and falha["gravadas"] == []


def test_custo_de_ia_em_usd_aguarda_ptax_e_converte_pela_do_dia(client, db_session, professional):  # noqa: F811
    definir_parametros(db_session, impostos=0.10, pool=[componente(0.0)], tier_padrao=None)
    resposta = client.post("/api/v1/comissoes/politica-margem", json={"deduzir_custo_ia": True, "motivo": "PO: IA na margem"})
    assert resposta.status_code == 201 and resposta.json()["versao"] == 2
    _execucao_ia(db_session, professional.tenant_id, 100, datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=1))
    recebimento = _receber(db_session, professional, "LICENSE", 100_000)
    dados = next(a for a in client.get("/api/v1/comissoes/apuracoes").json() if a["id"] == _apuracao(db_session, recebimento).id)
    assert dados["missing_parameters"] == ["FX_RATE"] and dados["commission_amount_status"] == "AWAITING_FX_RATE"
    resposta = client.post("/api/v1/comissoes/cotacoes-cambio", json={"taxa": 5.25, "fonte": "BANCO_CENTRAL_DO_BRASIL",
                                                                      "vigente_em": f"{date.today() - timedelta(days=40)}T00:00:00"})
    assert resposta.status_code == 201 and resposta.json()["aguardando_calculadas"] == 1
    apuracao = _apuracao(db_session, recebimento)
    db_session.refresh(apuracao)
    assert (apuracao.custo_ia, apuracao.margem_comissionavel_liquida) == (Decimal("525.00"), Decimal("89475.00"))  # 100.000 − 10.000 − 525
    assert db_session.query(AuditLog).filter_by(evento_tipo="cotacao_cambio_registrada").count() == 1


def test_politica_da_margem_so_define_custo_de_ia_e_exige_motivo(client):
    assert client.post("/api/v1/comissoes/politica-margem", json={"deduzir_custo_ia": True, "motivo": ""}).status_code == 422
    with pytest.raises(ValidacaoFalhou):
        comissoes.politica.nova(None, {"deduzir_custo_ia": True, "deduzir_impostos": False}, "tirar impostos", "teste")
    assert client.get("/api/v1/comissoes/parametros").json()["politica_margem"] == {"versao": 1, "regras": {"deduzir_custo_ia": False}}


def test_waterfall_mostra_impostos_por_tributo_e_pendencias_por_parametro(client, db_session, professional):  # noqa: F811
    _perfis_do_po(db_session)
    _receber(db_session, professional, "LICENSE", 120_000)  # sem pool: aguarda infraestrutura
    _pool_zero(db_session)
    comissoes.motor.recalcular_aguardando(db_session)
    db_session.commit()
    _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000)  # SaaS: ISS pendente
    total = client.get("/api/v1/comissoes/waterfall").json()["total"]
    assert total["impostos_por_tributo"] == {"CBS": 0.0, "COFINS": 3600.0, "CSLL": 3456.0, "IBS": 0.0, "IRPJ": 5760.0, "IRPJ_ADDITIONAL": 0.0,
                                             "ISS": 3480.0, "PIS": 780.0}
    assert total["aguardando_por_parametro"] == {"AWAITING_TAX_PROFILE": 1} and total["impostos"] == 17_076.0


def test_representante_privado_sem_tier_aguarda_infraestrutura(db_session):
    """Plano sem tier de infraestrutura: a mensalidade não tem peso para a alocação ponderada → aguarda (nada inventado)."""
    db_session.add_all([Tenant(id="priv-x", razao_social="X"), Plano(nome="Plano sem tier", franquia_contas_mes=0, preco_mensal=10.0,
                                                                    modulos_contratados=["crm"])])
    db_session.commit()
    plano = db_session.query(Plano).filter_by(nome="Plano sem tier").one()
    db_session.add(Licenca(tenant_id="priv-x", plano_id=plano.id, status="ativa"))
    rep = Representante(nome="R", email="r@x.com", chave_pix="p", percentual_comissao=0.2)
    db_session.add(rep)
    definir_parametros(db_session, pool=[componente(100.0)], tier_padrao=None)
    apuracao, _ = comissoes.motor.registrar_recebimento(
        db_session, origem=comissoes.tipos.Origem.PAGAMENTO_LICENCA, tenant_id="priv-x", segmento="PRIVATE", produto=plano.nome,
        tipo_receita="SAAS_SUBSCRIPTION", recebido_em=date.today(), receita_bruta=10, beneficiarios=[(rep.id, 1)], taxa=0.2,
        pagamento_licenca_id=None, recebimento_governo_id=None, meses_infra=1.0)
    assert apuracao.parametros_faltantes == ["INFRASTRUCTURE_COST"]
    assert apuracao.detalhe["infraestrutura"]["planos_sem_peso"] == ["Plano sem tier"]
