"""B2B ON Government (D-072): licença institucional + subscrição anual, AI Credits anuais, bookings/ARR/TCV/Cash-In,
renovação, comissão por componente e catálogo único (página pública e Admin → Planos)."""

import importlib.util
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.finops import contract as finops
from app.contexts.governo import contract as governo
from app.models.auditoria import AuditLog
from app.models.comissao_representante import ComissaoRepresentante
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from tests.parametros_comissao import definir_parametros
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

RAIZ = Path(__file__).resolve().parents[2]
G = "/api/v1/governo"
TENANT = "orgao-gov"
HOJE = date.today()


def _migracao(arquivo: str = "d9e1f3a5b7c9_b2bon_government.py"):
    caminho = RAIZ / "alembic/versions" / arquivo
    spec = importlib.util.spec_from_file_location(arquivo, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MIG = _migracao()
MIG_D073 = _migracao("e1f3a5b7c9d2_comissao_base_liquida.py")
MIG_D075 = _migracao("a6c8e0f2b4d7_parametros_financeiros_entitlements_gov.py")


@pytest.fixture()
def planos_gov(db_session):
    """Os três planos com os valores das migrações (a fonte que cria os planos em produção): preços da D-072 e
    entitlements da D-075."""
    criados = {}
    for nome, licenca, implantacao, assinatura, creditos, recomendado in MIG.PLANOS:
        usuarios, api, extras = MIG_D075.ENTITLEMENTS[nome]
        plano = Plano(nome=nome, franquia_contas_mes=0, max_usuarios=usuarios, preco_mensal=0.0, visivel_self_service=False,
                      modulos_contratados=list(MIG_D075.MODULOS), categoria="governo", tipo_preco="CONTRACT", segmento="GOVERNMENT",
                      modelo_cobranca=MIG.MODELO, preco_licenca=licenca, preco_implantacao=implantacao, preco_assinatura_anual=assinatura,
                      creditos_ia_anuais=creditos, recomendado=recomendado, permite_api_parceiros=api, entitlements=dict(extras))
        db_session.add(plano)
        criados[nome.split()[-1]] = plano
    for tenant_id in (TENANT, "orgao-outro"):
        db_session.add(Tenant(id=tenant_id, razao_social=f"Órgão {tenant_id}"))
    db_session.commit()
    return criados


@pytest.fixture()
def rep(db_session):
    """Representante. Parâmetros de custo zerados: Margem Comissionável Líquida = valor recebido, para conferir as taxas
    de cada componente. A margem com impostos, infraestrutura e IA tem testes próprios (`test_comissao_margem.py`)."""
    definir_parametros(db_session)

    def _criar(nome: str) -> Representante:
        r = Representante(nome=nome, email=f"{nome}@rep.com", chave_pix=f"{nome}-pix", percentual_comissao=0.1)
        db_session.add(r)
        db_session.commit()
        return r
    return _criar


def _contrato(db_session, plano, representante=None, tenant=TENANT, **extra):
    return governo.contratos.criar(db_session, tenant_id=tenant, plano_id=plano.id, modelo=extra.pop("modelo", MIG.MODELO),
                                   referencia_contrato=extra.pop("referencia", "CT-001/2026"), entidade_governamental="Prefeitura X",
                                   assinado_em=extra.pop("assinado_em", HOJE), representante_id=representante.id if representante else None,
                                   **extra)


def _componente(db_session, contrato, tipo):
    return next(c for c in governo.contratos.componentes(db_session, contrato) if c.tipo == tipo)


def _comissoes(db_session, **filtro):
    return db_session.query(ComissaoRepresentante).filter_by(**filtro).order_by(ComissaoRepresentante.id).all()


# 1, 2 — contratação inicial e separação dos componentes ------------------------------------------------------------
@pytest.mark.parametrize("tier,licenca,implantacao,assinatura,total,creditos", [
    ("Department", 72_000, 12_000, 24_000, 108_000, 300_000),
    ("Professional", 120_000, 20_000, 36_000, 176_000, 600_000),
    ("Enterprise", 180_000, 30_000, 54_000, 264_000, 1_200_000),
])
def test_contratacao_inicial_e_componentes_separados(db_session, planos_gov, tier, licenca, implantacao, assinatura, total, creditos):
    oferta = governo.ofertas.oferta(planos_gov[tier])
    assert (oferta["licenca"], oferta["implantacao"], oferta["assinatura_anual"], oferta["contratacao_inicial"],
            oferta["creditos_ia_anuais"], oferta["periodicidade"]) == (licenca, implantacao, assinatura, total, creditos, "ANUAL")
    contrato = _contrato(db_session, planos_gov[tier])
    tipos = {c.tipo: float(c.valor) for c in governo.contratos.componentes(db_session, contrato)}
    assert tipos == {"LICENSE": licenca, "IMPLEMENTATION": implantacao, "INITIAL_ANNUAL_SUBSCRIPTION": assinatura}
    assert governo.contratos.resumo(db_session, contrato)["valores"]["contratacao_inicial"] == total
    assert governo.ofertas.planos(db_session)[1].recomendado and governo.ofertas.planos(db_session)[1].nome.endswith("Professional")


# 3, 4, 5 — ARR só com subscrição; licença e implantação fora -------------------------------------------------------
def test_arr_bookings_tcv_e_cash_in(db_session, planos_gov):
    contrato = _contrato(db_session, planos_gov["Professional"])
    m = governo.analytics.metricas(db_session)
    assert m["bookings"] == {"licenca": 120_000, "servicos": 20_000, "assinatura": 36_000, "creditos": 0, "total": 176_000}
    assert (m["new_arr"], m["arr_governo"], m["tcv_inicial"], m["cash_in"]) == (36_000, 36_000, 176_000, 0)
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=_componente(db_session, contrato, "LICENSE").id,
                                   valor=40_000, recebido_em=HOJE)
    m = governo.analytics.metricas(db_session)
    assert m["cash_in"] == 40_000 and m["arr_governo"] == 36_000  # recebimento de licença não vira ARR


# 6 — renovação sem licença; 10% em todas as renovações; reajuste ------------------------------------------------------
def test_renovacao_nao_cobra_licenca_e_comissao_fica_em_10(db_session, planos_gov, rep):
    vendedor = rep("ana")
    contrato = _contrato(db_session, planos_gov["Professional"], vendedor, assinado_em=HOJE - timedelta(days=3 * 365 + 2))
    for numero, valor in ((2, None), (3, 37_800), (4, None)):
        periodo = governo.contratos.renovar(db_session, contrato.id, valor_assinatura=valor,
                                            motivo_reajuste="Reajuste contratual (cláusula 8ª)" if valor else None)
        assert periodo.numero == numero
        componente = next(c for c in governo.contratos.componentes(db_session, contrato) if c.periodo_id == periodo.id)
        governo.recebimentos.registrar(db_session, contrato.id, componente_id=componente.id, valor=componente.valor, recebido_em=HOJE)
    tipos = [c.tipo for c in governo.contratos.componentes(db_session, contrato)]
    assert tipos.count("LICENSE") == 1 and tipos.count("RENEWAL_ANNUAL_SUBSCRIPTION") == 3
    renovacoes = _comissoes(db_session, componente_tipo="RENEWAL_ANNUAL_SUBSCRIPTION")
    assert [(c.numero_renovacao, c.taxa, c.valor_comissao) for c in renovacoes] == [(1, 0.1, 3_600.0), (2, 0.1, 3_780.0), (3, 0.1, 3_780.0)]
    with pytest.raises(ValidacaoFalhou, match="motivo"):
        governo.contratos.renovar(db_session, contrato.id, valor_assinatura=40_000)


# 7, 8 — pool anual na carteira universal; expira e renova --------------------------------------------------------------
def test_pool_anual_de_ai_credits_expira_e_renova(db_session, planos_gov):
    contrato = _contrato(db_session, planos_gov["Department"], assinado_em=HOJE - timedelta(days=10))
    assert finops.carteira.franquia_do_tenant(db_session, TENANT)[0] == 0  # sem franquia mensal
    assert float(finops.carteira.disponivel(db_session, TENANT)) == 300_000
    periodo = governo.contratos.periodos(db_session, contrato)[0]
    pool = governo.contratos.pool(db_session, periodo)
    assert pool["annual_credit_pool"] == 300_000 and pool["credits_remaining"] == 300_000 and pool["tenant_id"] == TENANT
    assert pool["valid_until"].startswith(periodo.fim.isoformat()) and pool["credit_source"] == "POOL_ANUAL_GOVERNO"
    novo = governo.contratos.renovar(db_session, contrato.id)  # começa no fim do período atual: pool só quando chegar o dia
    assert novo.lote_creditos_id is None
    governo.contratos.rotina(db_session, dia=novo.inicio)
    finops.carteira.expirar_vencidos(db_session, TENANT, agora=finops.carteira.agora_utc() + timedelta(days=400))
    db_session.commit()
    assert governo.contratos.pool(db_session, periodo)["status"] == "EXPIRADO"
    assert governo.contratos.pool(db_session, governo.contratos.periodos(db_session, contrato)[1])["annual_credit_pool"] == 300_000


# 9 — isolamento de tenant ------------------------------------------------------------------------------------------
def test_cliente_ve_so_o_proprio_contrato_e_nunca_comissoes(client, db_session, planos_gov, rep, criar_usuario_autenticado):
    _contrato(db_session, planos_gov["Professional"], rep("bia"))
    _contrato(db_session, planos_gov["Department"], tenant="orgao-outro", referencia="CT-OUTRO")
    proprio = client.get(f"{G}/meu-contrato", headers=criar_usuario_autenticado(TENANT)).json()["contrato"]
    assert proprio["referencia_contrato"] == "CT-001/2026" and "representante_id" not in proprio
    assert all("comissionavel" not in c for c in proprio["componentes"])
    outro = criar_usuario_autenticado("orgao-outro", email="admin@outro.gov")
    assert client.get(f"{G}/meu-contrato", headers=outro).json()["contrato"]["referencia_contrato"] == "CT-OUTRO"
    for rota in ("/contratos", "/comissoes", "/metricas", "/oportunidades", "/planos"):  # 14 — só super_admin
        assert client.get(G + rota, headers=outro).status_code == 403
    with pytest.raises(NaoEncontrado):
        governo.contratos.obter(db_session, 1, tenant_id="orgao-outro")


# 10, 11, 13 (público) — página pública e Admin leem o mesmo catálogo -----------------------------------------------------
def test_pagina_publica_e_admin_iguais_ao_catalogo(client, db_session, planos_gov):
    catalogo = governo.ofertas.catalogo_publico(db_session)["planos"]
    publico = client.get("/api/v1/catalogo").json()["governo"]
    assert publico["planos"] == catalogo
    admin = {p["nome"]: p for p in client.get("/api/v1/planos").json() if p["segmento"] == "GOVERNMENT"}
    for oferta in catalogo:
        linha = admin[oferta["nome"]]
        assert (linha["preco_licenca"], linha["preco_implantacao"], linha["preco_assinatura_anual"], linha["creditos_ia_anuais"]) == (
            oferta["licenca"], oferta["implantacao"], oferta["assinatura_anual"], oferta["creditos_ia_anuais"])
        assert linha["modelo_cobranca"] == "GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION" and linha["tipo_preco"] == "CONTRACT"
    assert "Subscrição Anual" in publico["composicao"] and "subscrição anual disponível" in publico["so_assinatura"]
    fonte = "".join(p.read_text(encoding="utf-8") for p in (RAIZ / "frontend/src").rglob("*.tsx"))
    assert not any(valor in fonte for valor in ("72.000", "120.000", "180.000", "1.200.000", "176.000"))  # sem preço fixo no frontend


# 12 — mudar o preço não muda contrato antigo; mudança auditada --------------------------------------------------------
def test_alterar_preco_nao_altera_contrato_e_e_auditado(client, db_session, planos_gov):
    plano = planos_gov["Professional"]
    contrato = _contrato(db_session, plano)
    resposta = client.put(f"/api/v1/planos/{plano.id}", json={"nome": plano.nome, "franquia_contas_mes": 0, "preco_mensal": 0,
                                                              "preco_assinatura_anual": 39_000, "motivo": "Tabela 2027"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["segmento"] == "GOVERNMENT"  # campos não enviados não voltam ao padrão
    db_session.refresh(contrato)
    assert float(contrato.valor_assinatura_anual) == 36_000
    assert _componente(db_session, contrato, "INITIAL_ANNUAL_SUBSCRIPTION").valor == Decimal("36000.00")
    log = db_session.query(AuditLog).filter_by(evento_tipo="plano_alterado", entidade_id=plano.id).one()
    assert log.detalhes["mudancas"]["preco_assinatura_anual"] == {"antes": 36_000.0, "depois": 39_000.0}
    assert log.detalhes["motivo"] == "Tabela 2027" and log.ator_id


# 13 — Subscription Only -----------------------------------------------------------------------------------------------
def test_subscription_only_licenca_zero_valores_configuraveis_20_e_10(db_session, planos_gov, rep):
    vendedor = rep("caio")
    with pytest.raises(ValidacaoFalhou, match="Subscription Only"):
        _contrato(db_session, planos_gov["Professional"], vendedor, modelo="GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY")
    contrato = _contrato(db_session, planos_gov["Professional"], vendedor, modelo="GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY",
                         valores={"implantacao": 0, "assinatura_anual": 60_000, "creditos_ia_anuais": 500_000})
    assert {c.tipo for c in governo.contratos.componentes(db_session, contrato)} == {"INITIAL_ANNUAL_SUBSCRIPTION"}
    assert float(contrato.valor_licenca) == 0
    inicial = _componente(db_session, contrato, "INITIAL_ANNUAL_SUBSCRIPTION")
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=inicial.id, valor=60_000, recebido_em=HOJE)
    renovacao = governo.contratos.renovar(db_session, contrato.id)
    comp = next(c for c in governo.contratos.componentes(db_session, contrato) if c.periodo_id == renovacao.id)
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=comp.id, valor=60_000, recebido_em=HOJE)
    assert [c.valor_comissao for c in _comissoes(db_session, contrato_governo_id=contrato.id)] == [12_000.0, 6_000.0]


# 16 — planos privados intactos --------------------------------------------------------------------------------------
def test_planos_privados_sem_regressao(client, db_session, planos_gov, criar_plano):
    privado = criar_plano(nome="Starter", preco_mensal=924.5)
    catalogo = client.get("/api/v1/catalogo").json()
    assert all(p["nome"] not in {g.nome for g in planos_gov.values()} for p in catalogo["planos"])  # Government fora do checkout
    resposta = client.get("/api/v1/planos?apenas_self_service=true").json()
    assert {p["nome"] for p in resposta}.isdisjoint({g.nome for g in planos_gov.values()})
    db_session.refresh(privado)
    assert (privado.segmento, privado.modelo_cobranca, privado.preco_licenca, privado.creditos_ia_anuais) == (
        "PRIVATE", "MONTHLY_SUBSCRIPTION", None, None)
    erro = client.put(f"/api/v1/planos/{privado.id}", json={"nome": "Starter", "franquia_contas_mes": 200, "preco_mensal": 924.5,
                                                            "preco_licenca": 10})
    assert erro.status_code == 422


# Comissão --------------------------------------------------------------------------------------------------------------
def test_comissao_inicial_20_por_componente_implantacao_fora(db_session, planos_gov, rep):
    vendedor = rep("davi")
    contrato = _contrato(db_session, planos_gov["Professional"], vendedor)
    for tipo, valor in (("LICENSE", 120_000), ("IMPLEMENTATION", 20_000), ("INITIAL_ANNUAL_SUBSCRIPTION", 36_000)):
        governo.recebimentos.registrar(db_session, contrato.id, componente_id=_componente(db_session, contrato, tipo).id, valor=valor,
                                       recebido_em=HOJE)
    valores = {c.componente_tipo: c.valor_comissao for c in _comissoes(db_session, contrato_governo_id=contrato.id)}
    assert valores == {"LICENSE": 24_000.0, "INITIAL_ANNUAL_SUBSCRIPTION": 7_200.0}  # 156.000 × 20% = 31.200, nunca 176.000 × 20%
    m = governo.analytics.metricas(db_session)
    assert m["comissoes"]["inicial"] == 31_200 and m["receita_comissionavel"] == 156_000 and m["receita_nao_comissionavel"] == 20_000


def test_payment_received_parcelas_proporcionais_e_nada_antes(db_session, planos_gov, rep):
    contrato = _contrato(db_session, planos_gov["Professional"], rep("eva"))
    assert _comissoes(db_session, contrato_governo_id=contrato.id) == []  # contratado, nada recebido: sem comissão
    licenca = _componente(db_session, contrato, "LICENSE")
    for parcela in range(3):
        governo.recebimentos.registrar(db_session, contrato.id, componente_id=licenca.id, valor=40_000, recebido_em=HOJE,
                                       idempotency_key=f"p{parcela}")
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=licenca.id, valor=40_000, recebido_em=HOJE, idempotency_key="p2")
    assert [c.valor_comissao for c in _comissoes(db_session, contrato_governo_id=contrato.id)] == [8_000.0] * 3
    with pytest.raises(RegraNegocioViolada, match="acima"):
        governo.recebimentos.registrar(db_session, contrato.id, componente_id=licenca.id, valor=1, recebido_em=HOJE)


def test_politica_nova_torna_implantacao_comissionavel_sem_codigo(client, db_session, planos_gov, rep):
    regras = governo.politicas.politica_vigente(db_session).regras
    regras = {**regras, "componentes": {**regras["componentes"], "IMPLEMENTATION": {"comissionavel": True, "taxa": 0.2}}}
    resposta = client.post(f"{G}/politica-comissao", json={"regras": regras, "motivo": "Implantação passa a comissionar"})
    assert resposta.status_code == 201 and resposta.json()["versao"] == 2
    contrato = _contrato(db_session, planos_gov["Professional"], rep("fred"))
    implantacao = _componente(db_session, contrato, "IMPLEMENTATION")
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=implantacao.id, valor=20_000, recebido_em=HOJE)
    assert [c.valor_comissao for c in _comissoes(db_session, componente_governo_id=implantacao.id)] == [4_000.0]
    log = db_session.query(AuditLog).filter_by(evento_tipo="politica_comissao_alterada").one()
    assert log.detalhes["motivo"] == "Implantação passa a comissionar" and log.detalhes["versao"] == 2


def test_contrato_guarda_a_politica_em_que_nasceu(db_session, planos_gov, rep):
    antigo = _contrato(db_session, planos_gov["Department"], rep("hugo"), referencia="CT-V1")
    regras = governo.politicas.politica_vigente(db_session).regras
    governo.politicas.nova_politica(db_session, {**regras, "componentes": {**regras["componentes"],
                                                                           "IMPLEMENTATION": {"comissionavel": True, "taxa": 0.2}}},
                                    "teste", "admin")
    novo = _contrato(db_session, planos_gov["Department"], rep("iris"), referencia="CT-V2")
    assert _componente(db_session, antigo, "IMPLEMENTATION").comissionavel is False
    assert _componente(db_session, novo, "IMPLEMENTATION").comissionavel is True
    assert (antigo.politica_comissao_versao, novo.politica_comissao_versao) == (1, 2)


def test_so_recebimento_dispara_comissao(db_session, planos_gov, rep):
    regras = governo.politicas.politica_vigente(db_session).regras
    for gatilho in ("CONTRACT_SIGNED", "INVOICE_ISSUED"):  # D-074: nunca antes do recebimento
        with pytest.raises(ValidacaoFalhou, match="gatilho"):
            governo.politicas.nova_politica(db_session, {**regras, "gatilho": gatilho}, "teste", "admin")
    contrato = _contrato(db_session, planos_gov["Professional"], rep("joao"))
    assert _comissoes(db_session, contrato_governo_id=contrato.id) == []


def test_estorno_anula_ou_gera_clawback(db_session, planos_gov, rep):
    contrato = _contrato(db_session, planos_gov["Professional"], rep("kai"))
    licenca = _componente(db_session, contrato, "LICENSE")
    r1 = governo.recebimentos.registrar(db_session, contrato.id, componente_id=licenca.id, valor=40_000, recebido_em=HOJE)
    r2 = governo.recebimentos.registrar(db_session, contrato.id, componente_id=licenca.id, valor=40_000, recebido_em=HOJE)
    pago = _comissoes(db_session, recebimento_governo_id=r2.id)[0]
    pago.status = "PAID"
    db_session.commit()
    assert governo.recebimentos.estornar(db_session, r1.id, "Ordem bancária devolvida") == {"anuladas": 1, "a_compensar": 0}
    assert governo.recebimentos.estornar(db_session, r2.id, "Glosa") == {"anuladas": 0, "a_compensar": 1}
    clawback = _comissoes(db_session, recebimento_governo_id=r2.id, evento="CLAWBACK")[0]
    assert clawback.valor_comissao == -8_000.0 and clawback.status == "CLAWBACK_PENDING"
    assert governo.analytics.metricas(db_session)["cash_in"] == 0


def test_transferencia_preserva_historico_e_override_exige_aprovacao(client, db_session, planos_gov, rep):
    original, novo = rep("lia"), rep("max")
    contrato = _contrato(db_session, planos_gov["Professional"], original)
    assinatura = _componente(db_session, contrato, "INITIAL_ANNUAL_SUBSCRIPTION")
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=assinatura.id, valor=18_000, recebido_em=HOJE)
    sem_aprovador = client.post(f"{G}/contratos/{contrato.id}/transferencia-comissao", json={"representante_id": novo.id, "motivo": "x"})
    assert sem_aprovador.status_code == 422
    resposta = client.post(f"{G}/contratos/{contrato.id}/transferencia-comissao", json={
        "divisao": [{"representante_id": original.id, "fracao": 0.5}, {"representante_id": novo.id, "fracao": 0.5}],
        "motivo": "Divisão da conta", "aprovado_por": "diretoria"})
    assert resposta.status_code == 200, resposta.text
    governo.recebimentos.registrar(db_session, contrato.id, componente_id=assinatura.id, valor=18_000, recebido_em=HOJE)
    linhas = [(c.representante_id, c.valor_comissao) for c in _comissoes(db_session, contrato_governo_id=contrato.id)]
    assert linhas == [(original.id, 3_600.0), (original.id, 1_800.0), (novo.id, 1_800.0)]
    override = client.patch(f"{G}/componentes/{assinatura.id}/comissao", json={"taxa": 0.15, "motivo": "Acordo", "aprovado_por": "cfo"})
    assert override.status_code == 200 and override.json()["taxa_comissao"] == 0.15
    eventos = {log.evento_tipo for log in db_session.query(AuditLog).filter(AuditLog.evento_tipo.like("comissao_governo%"))}
    assert eventos == {"comissao_governo_transferida", "comissao_governo_override"}


def test_desconto_exige_motivo_e_fica_auditado(db_session, planos_gov):
    with pytest.raises(ValidacaoFalhou, match="motivo"):
        _contrato(db_session, planos_gov["Professional"], valores={"licenca": 100_000})
    contrato = _contrato(db_session, planos_gov["Professional"], valores={"licenca": 100_000}, motivo_valores="Preço do edital")
    log = db_session.query(AuditLog).filter_by(evento_tipo="contrato_governo_criado", entidade_id=contrato.id).one()
    assert log.detalhes["negociado"] is True and log.detalhes["catalogo"]["licenca"] == 120_000


def test_pipeline_ponderado_e_proposta_por_template(client, db_session, planos_gov):
    criada = client.post(f"{G}/oportunidades", json={
        "titulo": "Plataforma de compras", "entidade_governamental": "Estado Y", "estagio": "RFP_EDITAL_TR",
        "valor_estimado_licenca": 120_000, "valor_estimado_assinatura": 36_000, "valor_estimado_servicos": 20_000, "probabilidade": 0.25,
        "data_prevista_fechamento": (HOJE + timedelta(days=120)).isoformat(), "referencia_processo": "PE 12/2026"}).json()
    assert criada["tcv_estimado"] == 176_000 and criada["pipeline_ponderado"] == 44_000
    assert client.post(f"{G}/oportunidades", json={"titulo": "x", "entidade_governamental": "y", "estagio": "GANHO"}).status_code == 422
    proposta = client.post(f"{G}/planos/{planos_gov['Professional'].id}/proposta", json={"entidade_governamental": "Estado Y"}).json()
    assert "LICENÇA INSTITUCIONAL: R$ 120.000,00" in proposta["texto"] and "CONTRATAÇÃO INICIAL: R$ 176.000,00" in proposta["texto"]
    assert "R$ 36.000,00/ano" in proposta["texto"]


def test_politica_e_template_iniciais_iguais_a_migracao():
    assert governo.tipos.POLITICA_INICIAL == MIG.POLITICA_V1
    assert governo.tipos.POLITICA_ATUAL == MIG_D073.POLITICA_V2
    assert governo.tipos.TEMPLATE_PROPOSTA_INICIAL == MIG.TEMPLATE_V1
    assert all(set(extras) == set(governo.tipos.CHAVES_ENTITLEMENT) for _, _, extras in MIG_D075.ENTITLEMENTS.values())
