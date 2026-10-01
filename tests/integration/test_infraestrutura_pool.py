"""D-076: Infrastructure Cost Pool — custo real × provisionado (plano máximo), alocação ponderada por tier, atribuição
direta, sem dupla contagem com IA/APIs, capacidade (70/80/90/100%), alertas sem ação automática, projeção e Provider
Economics. Todos os fornecedores e valores aqui são de teste."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.contexts.comissoes import contract as comissoes
from app.contexts.finops import contract as finops
from app.models.auditoria import AuditLog
from app.models.custo_infraestrutura import AlertaCapacidadeInfra, ComponenteInfra
from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.services.errors import ValidacaoFalhou
from tests.parametros_comissao import componente

HOJE = date.today()
TENANTS = {"t-dep": "DEPARTMENT", "t-pro": "PROFESSIONAL", "t-ent": "ENTERPRISE"}


@pytest.fixture()
def tenants(db_session):
    planos = {}
    for tenant_id, tier in TENANTS.items():
        plano = Plano(nome=f"Plano {tier}", franquia_contas_mes=0, preco_mensal=1000.0, modulos_contratados=["crm"], tier_infraestrutura=tier)
        db_session.add_all([plano, Tenant(id=tenant_id, razao_social=tier)])
        db_session.flush()
        db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
        planos[tenant_id] = plano
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": date(2000, 1, 1),
                                          "componentes": [{"tributo": "OTHER_TAX", "base": "RECEITA", "aliquota": 0.0}]}, "teste")
    db_session.commit()
    return planos


def _criar(db, custo_referencia=7000.0, **extra):
    item = comissoes.infraestrutura.criar(db, componente(custo_referencia, **extra), "teste")
    db.commit()
    return item


def _receber(db, planos, tenant_id, valor=1000.0, rep=None):
    pagamento = PagamentoLicenca(tenant_id=tenant_id, plano_id=planos[tenant_id].id, preferencia_id_externo=f"pref-{tenant_id}-{valor}",
                                 status="aprovado", valor=valor)
    db.add(pagamento)
    db.flush()
    apuracao, geradas = comissoes.motor.registrar_recebimento(
        db, origem=comissoes.tipos.Origem.PAGAMENTO_LICENCA, tenant_id=tenant_id, segmento="PRIVATE", produto=planos[tenant_id].nome,
        tipo_receita="SAAS_SUBSCRIPTION", recebido_em=HOJE, receita_bruta=valor, beneficiarios=[(rep.id, 1)] if rep else [],
        taxa=0.2 if rep else None, pagamento_licenca_id=pagamento.id, meses_infra=1.0)
    db.commit()
    return apuracao, geradas


def test_pesos_iniciais_e_alocacao_ponderada(db_session, tenants):
    assert comissoes.politica.vigente_infra(db_session).regras["pesos"] == {
        "STARTER": 1.0, "DEPARTMENT": 1.0, "PROFESSIONAL": 2.0, "ENTERPRISE": 4.0, "BID_INTELLIGENCE": 2.0, "STRATEGIC_SOURCING": 4.0}
    _criar(db_session, 7000.0)
    dados = comissoes.infraestrutura.pool(db_session, HOJE)
    assert dados["unidades"] == 7  # 1 + 2 + 4: não é custo ÷ número de clientes
    custos = {t: comissoes.infraestrutura.custo_tenant_mensal(dados, t)[0] for t in TENANTS}
    assert custos == {"t-dep": Decimal("1000.00"), "t-pro": Decimal("2000.00"), "t-ent": Decimal("4000.00")}


def test_custo_real_e_provisionado_separados_e_plano_maximo_nao_cai_com_uso_baixo(db_session, tenants):
    _criar(db_session, 7000.0, custo_contratado=3000.0, custo_real=2100.0, capacidade_contratada=100, uso_atual=10)
    apuracao, _ = _receber(db_session, tenants, "t-pro")
    assert (apuracao.custo_infra, apuracao.custo_infra_real) == (Decimal("2000.00"), Decimal("600.00"))
    assert apuracao.margem_comissionavel_liquida == Decimal("-1000.00")  # comissão usa o provisionado (conservador)
    economia = comissoes.capacidade.economia_fornecedores(db_session)
    assert (economia["resumo"]["pool_provisionado_mensal"], economia["resumo"]["pool_real_mensal"], economia["resumo"]["reserva_mensal"]) == (
        7000.0, 2100.0, 4900.0)


def test_comissao_usa_a_politica_configurada(db_session, tenants):
    rep = Representante(nome="R", email="r@infra.com", chave_pix="p", percentual_comissao=0.2)
    db_session.add(rep)
    _criar(db_session, 700.0, custo_real=350.0)
    _, (provisionada,) = _receber(db_session, tenants, "t-pro", 1000.0, rep)
    assert provisionada.valor_comissao == 160.0  # (1.000 − 200 provisionado) × 20%
    nova = dict(comissoes.politica.vigente_infra(db_session).regras, custo_comissao="ACTUAL")
    comissoes.politica.nova_infra(db_session, nova, "Simulação com custo real", "teste")
    _, (real,) = _receber(db_session, tenants, "t-pro", 1001.0, rep)
    assert real.valor_comissao == 180.2  # (1.001 − 100 real) × 20%


def test_pesos_configuraveis_versionados_e_auditados(client, db_session, tenants):
    _criar(db_session, 1000.0)
    regras = {"pesos": {"STARTER": 1, "DEPARTMENT": 1, "PROFESSIONAL": 3, "ENTERPRISE": 6, "BID_INTELLIGENCE": 2, "STRATEGIC_SOURCING": 4},
              "limiares": {"ATTENTION": 0.7, "REVIEW": 0.8, "CRITICAL": 0.9, "CAPACITY_REACHED": 1.0}, "custo_comissao": "PROVISIONED"}
    resposta = client.post("/api/v1/comissoes/politica-infraestrutura", json={**regras, "motivo": "Revisão de pesos"})
    assert resposta.status_code == 201 and resposta.json()["versao"] == 2
    dados = comissoes.infraestrutura.pool(db_session, HOJE)
    assert dados["unidades"] == 10 and comissoes.infraestrutura.custo_tenant_mensal(dados, "t-ent")[0] == Decimal("600.00")
    assert db_session.query(AuditLog).filter_by(evento_tipo="politica_comissao_alterada").count() == 1
    for errado in ({**regras, "pesos": {"PROFESSIONAL": -1}}, {**regras, "limiares": {**regras["limiares"], "REVIEW": 0.95}},
                   {**regras, "custo_comissao": "GROSS"}):
        assert client.post("/api/v1/comissoes/politica-infraestrutura", json={**errado, "motivo": "x"}).status_code == 422
    assert client.post("/api/v1/comissoes/politica-infraestrutura", json={**regras, "motivo": ""}).status_code == 422


def test_atribuicao_direta_tem_prioridade_e_nao_vaza_entre_tenants(db_session, tenants):
    _criar(db_session, 0.0)
    direto = _criar(db_session, 1000.0, fornecedor="Lusha", servico="Créditos de enriquecimento", categoria="DATA_PROVIDER",
                    metodo_alocacao="DIRECT")
    comissoes.infraestrutura.registrar_custo_direto(db_session, {"componente_id": direto.id, "tenant_id": "t-pro",
                                                                 "competencia": HOJE.strftime("%Y-%m"), "custo": 300, "quantidade": 120}, "teste")
    db_session.commit()
    # o medido (300) vai direto ao t-pro; o restante do plano (700) volta ao pool ponderado: 100 por unidade
    pro, _ = _receber(db_session, tenants, "t-pro")
    dep, _ = _receber(db_session, tenants, "t-dep")
    assert (pro.custo_infra, dep.custo_infra) == (Decimal("500.00"), Decimal("100.00"))
    pro2, _ = _receber(db_session, tenants, "t-pro", 1002.0)
    assert pro2.custo_infra == Decimal("200.00")  # custo direto já atribuído não se repete
    with pytest.raises(ValidacaoFalhou, match="DIRECT"):
        comissoes.infraestrutura.registrar_custo_direto(db_session, {"componente_id": _criar(db_session, 1.0, servico="Outro").id, "tenant_id": "t-pro",
                                                                     "competencia": "2026-10", "custo": 1}, "teste")


def test_sem_dupla_contagem_de_ia_e_apis_ja_no_finops(db_session, tenants):
    _criar(db_session, 700.0)
    api = _criar(db_session, 9000.0, fornecedor="Provedor de dados", servico="API paga", categoria="APIS", contabilizacao="AI_COST",
                 metodo_alocacao="DIRECT")
    comissoes.infraestrutura.registrar_custo_direto(db_session, {"componente_id": api.id, "tenant_id": "t-pro",
                                                                 "competencia": HOJE.strftime("%Y-%m"), "custo": 500}, "teste")
    db_session.commit()
    apuracao, _ = _receber(db_session, tenants, "t-pro")
    assert apuracao.custo_infra == Decimal("200.00")  # só o pool de infraestrutura; a API já está no custo de IA/dados
    linha = next(c for c in comissoes.capacidade.economia_fornecedores(db_session)["componentes"] if c["id"] == api.id)
    assert linha["contabilizacao"] == "AI_COST" and linha["participacao_pool"] is None


@pytest.mark.parametrize(("uso", "esperado"), [(69, "NORMAL"), (70, "ATTENTION"), (80, "REVIEW"), (90, "CRITICAL"), (100, "CAPACITY_REACHED")])
def test_limiares_de_capacidade(db_session, tenants, uso, esperado):
    item = _criar(db_session, 1000.0, capacidade_contratada=100)
    assert comissoes.capacidade.registrar_uso(db_session, item.id, uso, "teste")["status"] == esperado


def test_alertas_80_90_100_exigem_decisao_humana_e_nada_muda_sozinho(client, db_session, tenants):
    item = _criar(db_session, 1000.0, capacidade_contratada=100, plano="Pro", plano_referencia="Max")
    mensagens = [comissoes.capacidade.registrar_uso(db_session, item.id, uso, "teste")["alerta"] for uso in (50, 82, 85, 91, 100)]
    db_session.commit()
    assert [m["mensagem"] if m else None for m in mensagens] == [
        None, "Revisar capacidade e condições comerciais do fornecedor: avaliar plano superior, contrato Enterprise, desconto por "
              "volume, parceria comercial, arquitetura ou novo fornecedor.", None,
        "Capacidade próxima do limite. Avaliar upgrade, contrato Enterprise, desconto por volume ou parceria estratégica.",
        "Contracted capacity reached."]
    db_session.refresh(item)
    assert (item.plano, item.plano_referencia, item.custo_referencia, item.capacidade_contratada) == ("Pro", "Max", Decimal("1000.00"), 100)
    alerta = db_session.query(AlertaCapacidadeInfra).filter_by(nivel="CAPACITY_REACHED").one()
    assert alerta.status == "ABERTO"
    resposta = client.post(f"/api/v1/comissoes/infraestrutura/alertas/{alerta.id}/decisao", json={"decisao": "Negociar contrato Enterprise"})
    assert resposta.status_code == 200 and resposta.json()["status"] == "DECIDIDO"
    db_session.refresh(item)
    assert item.plano == "Pro"  # a decisão é registrada; nenhum upgrade é feito pela plataforma


def test_limiares_configuraveis(db_session, tenants):
    item = _criar(db_session, 1000.0, capacidade_contratada=100)
    regras = dict(comissoes.politica.vigente_infra(db_session).regras,
                  limiares={"ATTENTION": 0.5, "REVIEW": 0.6, "CRITICAL": 0.7, "CAPACITY_REACHED": 0.8})
    comissoes.politica.nova_infra(db_session, regras, "Mais cedo", "teste")
    assert comissoes.capacidade.registrar_uso(db_session, item.id, 65, "teste")["status"] == "REVIEW"


def test_projecao_deterministica_de_esgotamento(db_session, tenants):
    item = _criar(db_session, 1000.0, capacidade_contratada=1000)
    inicio = datetime(2026, 9, 1)
    comissoes.capacidade.registrar_uso(db_session, item.id, 100, "teste", medido_em=inicio)
    comissoes.capacidade.registrar_uso(db_session, item.id, 200, "teste", medido_em=inicio + timedelta(days=10))
    projecao = comissoes.capacidade.projecao(db_session, item)
    assert projecao["inclinacao_dia"] == 10.0 and projecao["utilizacao_projetada"]["30d"] == 0.5
    assert projecao["esgotamento_estimado"] == (inicio + timedelta(days=90)).date().isoformat()


def test_provider_economics_api_e_isolamento(client, db_session, tenants, criar_usuario_autenticado):
    resposta = client.post("/api/v1/comissoes/infraestrutura/componentes", json={
        "fornecedor": "Render", "servico": "Web services", "categoria": "HOSTING", "plano": "Team", "plano_referencia": "Organization",
        "ciclo_cobranca": "ANNUAL", "moeda": "BRL", "custo_referencia": 84000, "custo_real": 24000, "capacidade_contratada": 100,
        "uso_atual": 40, "vigente_de": "2000-01-01"})
    assert resposta.status_code == 201
    dados = client.get("/api/v1/comissoes/infraestrutura").json()
    linha = dados["economia"]["componentes"][0]
    assert (linha["custo_provisionado_mensal_brl"], linha["custo_real_mensal_brl"], linha["custo_por_unidade_ponderada"],
            linha["utilizacao"], linha["status"]) == (7000.0, 2000.0, 1000.0, 0.4, "NORMAL")
    assert dados["economia"]["resumo"]["dependencia_maior_fornecedor"] == {"fornecedor": "Render", "participacao": 1.0}
    assert dados["economia"]["resumo"]["custo_sobre_receita"] == 2.3333  # 7.000 ÷ MRR 3.000
    log = db_session.query(AuditLog).filter_by(evento_tipo="componente_infra_criado").one()
    assert log.detalhes["depois"]["fornecedor"] == "Render"
    cabecalho = criar_usuario_autenticado("t-dep")
    for rota in ("/api/v1/comissoes/infraestrutura", "/api/v1/comissoes/parametros"):
        assert client.get(rota, headers=cabecalho).status_code == 403


def test_alteracao_de_custo_auditada_com_antes_e_depois(client, db_session, tenants):
    item = _criar(db_session, 1000.0)
    resposta = client.patch(f"/api/v1/comissoes/infraestrutura/componentes/{item.id}",
                            json={"dados": {"custo_referencia": 1500, "metodo_alocacao": "WEIGHTED"}, "motivo": "Novo plano máximo"})
    assert resposta.status_code == 200
    log = db_session.query(AuditLog).filter_by(evento_tipo="componente_infra_alterado").one()
    assert (log.detalhes["antes"]["custo_referencia"], log.detalhes["depois"]["custo_referencia"]) == ("1000.00", "1500")
    assert client.patch(f"/api/v1/comissoes/infraestrutura/componentes/{item.id}", json={"dados": {}, "motivo": ""}).status_code == 422


def test_componente_em_dolar_aguarda_ptax_e_guarda_snapshot(db_session, tenants):
    _criar(db_session, 1400.0, moeda="USD")
    apuracao, _ = _receber(db_session, tenants, "t-ent")
    assert apuracao.parametros_faltantes == ["FX_RATE"]
    finops.cambio.registrar(db_session, {"moeda_base": "USD", "moeda_cotacao": "BRL", "taxa": 5.0, "fonte": "BANCO_CENTRAL_DO_BRASIL",
                                         "tipo": "PTAX_CLOSE", "data_cotacao": HOJE - timedelta(days=1)}, "teste")
    comissoes.motor.recalcular_aguardando(db_session)
    db_session.commit()
    db_session.refresh(apuracao)
    assert apuracao.custo_infra == Decimal("4000.00")  # 1.400 USD × 5,00 = 7.000 ÷ 7 unidades × 4
    fx = apuracao.detalhe["infraestrutura"]["componentes"][0]["fx"]
    assert (fx["fx_rate"], fx["fx_date"], fx["source"], fx["type"]) == (5.0, (HOJE - timedelta(days=1)).isoformat(),
                                                                         "BANCO_CENTRAL_DO_BRASIL", "PTAX_CLOSE")
    assert db_session.query(ComponenteInfra).count() == 1
