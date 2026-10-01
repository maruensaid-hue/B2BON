"""MAP Performance Comercial (D-080): quota, attainment, cobertura 3x, funil, aprendizado, comissão recorrente,
inadimplência, cancelamento, campanha 100/120/150%, carteira histórica fora do bônus, separação do Governo, isolamento
por tenant, permissões e custo de consultas constante."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.contexts.map import contract as map_contract
from app.contexts.map.performance import campanha, configuracao, painel
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.atividade import Atividade
from app.models.auditoria import AuditLog
from app.models.comissao_representante import ComissaoRepresentante
from app.models.conta import Conta
from app.models.contrato_governo import OportunidadeGoverno
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.evento_dominio import EventoDominio
from app.models.licenca import Licenca
from app.models.negocio import Negocio
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.proposta_negocio import PropostaNegocio
from app.models.representante import Representante
from app.models.reuniao import Reuniao
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service, cron_repasse_comissoes_service
from app.services.errors import NaoAutorizado, ValidacaoFalhou
from app.providers.channels.email.stub import StubEmailProvider
from tests.fakes import FakePayoutProvider

OPERADOR = "cyberfort"
HOJE = date(2026, 10, 15)
DIA = datetime(2026, 10, 14, 10, 0)


def _operador(db):
    if db.get(Tenant, OPERADOR) is None:
        db.add(Tenant(id=OPERADOR, razao_social="CyberFort"))
        db.flush()


def _rep(db, nome="Ana", com_usuario=True) -> Representante:
    _operador(db)
    usuario = None
    if com_usuario:
        usuario = Usuario(tenant_id=OPERADOR, nome=nome, email=f"{nome.lower()}@cyberfort.com.br", papel="user", ativo=True)
        db.add(usuario)
        db.flush()
    rep = Representante(nome=nome, email=f"{nome.lower()}@rep.com", chave_pix="pix", percentual_comissao=0.2,
                        usuario_id=usuario.id if usuario else None)
    db.add(rep)
    db.flush()
    return rep


def _plano(db, nome="Suite", categoria="suite", modulos=("crm", "map", "predator"), segmento="PRIVATE") -> Plano:
    plano = db.query(Plano).filter_by(nome=nome).one_or_none()
    if plano is None:
        plano = Plano(nome=nome, franquia_contas_mes=0, preco_mensal=0.0, modulos_contratados=list(modulos), categoria=categoria,
                      segmento=segmento)
        db.add(plano)
        db.flush()
    return plano


def _cliente(db, rep, tenant_id, valor, primeiro_em: datetime, plano=None, pagamentos=(), ativa=True) -> Tenant:
    plano = plano or _plano(db)
    db.add(Tenant(id=tenant_id, razao_social=f"Cliente {tenant_id}", representante_id=rep.id))
    db.flush()
    db.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa" if ativa else "expirada"))
    for em in (primeiro_em, *pagamentos):
        db.add(PagamentoLicenca(tenant_id=tenant_id, plano_id=plano.id, preferencia_id_externo=f"p-{tenant_id}-{em}", status="aprovado",
                                valor=valor, confirmado_em=em))
    db.flush()
    return db.get(Tenant, tenant_id)


def _comissao(db, rep, tenant_id, valor, recebido_em: date, status="PAYABLE") -> ComissaoRepresentante:
    apuracao = ApuracaoComissao(tenant_id=tenant_id, origem="PAGAMENTO_LICENCA", segmento="PRIVATE", produto="Suite",
                                tipo_receita="SAAS_SUBSCRIPTION", recebido_em=recebido_em, receita_bruta=Decimal("1000"), status="CALCULATED")
    db.add(apuracao)
    db.flush()
    pagamento = next((pg for pg in db.query(PagamentoLicenca).filter_by(tenant_id=tenant_id).all()
                      if pg.confirmado_em.date() == recebido_em), None)
    if pagamento is None:  # recebimento sem pagamento próprio no cenário: cria um
        plano_id = db.query(PagamentoLicenca.plano_id).filter_by(tenant_id=tenant_id).first()[0]
        pagamento = PagamentoLicenca(tenant_id=tenant_id, plano_id=plano_id, preferencia_id_externo=f"x-{tenant_id}-{recebido_em}",
                                     status="aprovado", valor=0.0, confirmado_em=datetime.combine(recebido_em, datetime.min.time()))
        db.add(pagamento)
        db.flush()
    comissao = ComissaoRepresentante(representante_id=rep.id, tenant_id=tenant_id, pagamento_licenca_id=pagamento.id, apuracao_id=apuracao.id,
                                     valor_comissao=valor, status=status)
    db.add(comissao)
    db.flush()
    return comissao


def _estagios(db, tenant=OPERADOR):
    if not db.query(EstagioFunil).filter_by(tenant_id=tenant).first():
        db.add_all([EstagioFunil(tenant_id=tenant, nome=n, ordem=o, tipo=t)
                    for n, o, t in (("Descoberta", 1, "aberto"), ("Proposta", 2, "aberto"), ("Ganho", 3, "ganho"))])
        db.flush()
    return {e.tipo if e.tipo != "aberto" else e.nome: e for e in db.query(EstagioFunil).filter_by(tenant_id=tenant).all()}


def _conta(db, nome, icp=True, persona=True, tenant=OPERADOR) -> Conta:
    conta = Conta(tenant_id=tenant, nome=nome, status="prospectada", score_aderencia=0.9 if icp else 0.1)
    db.add(conta)
    db.flush()
    if persona:
        db.add(Decisor(tenant_id=tenant, conta_id=conta.id, nome=f"Decisor {nome}"))
        db.flush()
    return conta


def _negocio(db, rep, conta, valor, criado_em=DIA, estagio="Descoberta", prob=50, tenant=OPERADOR, ganho_em=None) -> Negocio:
    estagios = _estagios(db, tenant)
    negocio = Negocio(tenant_id=tenant, conta_id=conta.id, vendedor_usuario_id=rep.usuario_id,
                      estagio_id=estagios["ganho" if ganho_em else estagio].id, nome=f"Negócio {conta.nome}", valor=valor,
                      probabilidade=prob, origem="manual", criado_em=criado_em, atualizado_em=criado_em, ganho_em=ganho_em)
    db.add(negocio)
    db.flush()
    return negocio


def _atividade(db, rep, conta, tipo="ligacao", em=DIA, humano=True, negocio=None):
    db.add(Atividade(tenant_id=conta.tenant_id, conta_id=conta.id, negocio_id=negocio.id if negocio else None,
                     usuario_id=rep.usuario_id if humano else None, tipo=tipo, descricao="ação", criado_em=em))
    db.flush()


def _painel(db, rep, competencia="2026-10", hoje=HOJE):
    return painel.calcular(db, [rep], competencia, hoje)["paineis"][0]


def _headers(usuario) -> dict:
    return {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}


# ---------------------------------------------------------------- quota, attainment, cobertura

def test_quotas_do_po_por_representante_e_equipe(db_session):
    reps = [_rep(db_session, f"Rep{i}") for i in range(7)]
    esperado = {"2026-10": 7500, "2026-11": 10000, "2026-12": 12500, "2027-01": 15000, "2027-02": 17500, "2027-03": 20000}
    quotas = configuracao.quotas(db_session, list(esperado), [r.id for r in reps])
    for competencia, valor in esperado.items():
        assert {quotas[(r.id, competencia)].valor for r in reps} == {valor}
        assert sum(quotas[(r.id, competencia)].valor for r in reps) == valor * 7  # 52.500 … 140.000
    assert quotas[(reps[0].id, "2026-10")].pipeline_alvo == 30000
    equipe = painel.calcular(db_session, reps, "2026-10", HOJE)["equipe"]
    assert (equipe["quota"], equipe["representantes"]) == (52500, 7)


def test_quota_especifica_versionada_e_auditada(db_session):
    rep = _rep(db_session)
    configuracao.definir_quota(db_session, {"representante_id": rep.id, "competencia": "2026-11", "valor": 12000}, "Território maior", "gestor")
    nova = configuracao.definir_quota(db_session, {"representante_id": rep.id, "competencia": "2026-11", "valor": 11000}, "Ajuste", "gestor")
    assert (nova.versao, configuracao.quotas(db_session, ["2026-11"], [rep.id])[(rep.id, "2026-11")].valor) == (2, 11000)
    assert db_session.query(AuditLog).filter_by(evento_tipo="quota_comercial_definida").count() == 2
    with pytest.raises(ValidacaoFalhou):
        configuracao.definir_quota(db_session, {"competencia": "2026-13", "valor": 1}, "x", "gestor")


def test_attainment_gap_cobertura_3x_e_forecast(db_session):
    rep = _rep(db_session)
    _cliente(db_session, rep, "c1", 3000.0, datetime(2026, 10, 5))
    _cliente(db_session, rep, "c-set", 9999.0, datetime(2026, 9, 20))  # mês anterior: não é New MRR de outubro
    _negocio(db_session, rep, _conta(db_session, "Alfa"), 6000.0, prob=50)
    _negocio(db_session, rep, _conta(db_session, "Beta"), 3000.0, criado_em=datetime(2026, 10, 1), prob=40)
    p = _painel(db_session, rep)
    assert (p["quota"], p["realizado_new_mrr"], p["attainment"], p["gap"]) == (7500, 3000.0, 0.4, 4500.0)
    assert (p["pipeline"]["qualificado_mrr"], p["pipeline"]["cobertura"], p["pipeline"]["alvo"]) == (9000.0, 1.2, 30000.0)
    # forecast = realizado + ponderado dos que fecham no mês (UNCLASSIFIED → CORE 45 dias: nenhum fecha em outubro)
    assert p["forecast_new_mrr"] == 3000.0
    codigos = [a["codigo"] for a in p["alertas"]]
    assert "PIPELINE_COVERAGE_LOW" in codigos and "QUOTA_AT_RISK" in codigos


def test_forecast_usa_velocidade_da_familia(db_session):
    rep = _rep(db_session)
    regras = dict(configuracao.performance(db_session))
    regras["familia_por_oferta"] = {"7": "PREDATOR"}  # FAST, 15 dias
    configuracao.nova_politica(db_session, configuracao.CODIGO_POLITICA_PERFORMANCE, regras, "PREDATOR rápido", "gestor")
    negocio = _negocio(db_session, rep, _conta(db_session, "Gama"), 2000.0, prob=50)
    negocio.oferta_id = 7
    db_session.flush()
    p = _painel(db_session, rep)
    assert p["forecast_new_mrr"] == 1000.0 and p["velocidade"]["FAST"]["negocios"] == 1


# ---------------------------------------------------------------- funil e atividade

def test_conta_trabalhada_exige_icp_persona_e_acao_humana(db_session):
    rep = _rep(db_session)
    valida, sem_persona, sem_icp, automatica = (_conta(db_session, "V"), _conta(db_session, "SP", persona=False),
                                                _conta(db_session, "SI", icp=False), _conta(db_session, "A"))
    for conta in (valida, sem_persona, sem_icp):
        _atividade(db_session, rep, conta)
    _atividade(db_session, rep, automatica, humano=False)  # disparo automático: nunca conta
    _atividade(db_session, rep, valida, tipo="email")  # 2º toque = follow-up
    funil = _painel(db_session, rep)["funil_mes"]
    assert (funil["contas_trabalhadas"], funil["primeiros_toques"], funil["follow_ups"], funil["contatos_efetivos"]) == (1, 3, 1, 3)


def test_funil_completo_e_metas_de_atividade(db_session):
    rep = _rep(db_session)
    conta = _conta(db_session, "Funil")
    _atividade(db_session, rep, conta, tipo="reuniao")
    db_session.add(Reuniao(tenant_id=OPERADOR, conta_id=conta.id, decisor_id=1, vendedor_id=str(rep.usuario_id), data_hora=DIA, status="realizada"))
    negocio = _negocio(db_session, rep, conta, 1750.0)
    db_session.add(PropostaNegocio(tenant_id=OPERADOR, negocio_id=negocio.id, versao=1, nome_arquivo="p.pdf", tipo_mime="application/pdf",
                                   conteudo=b"x", tamanho_bytes=1, criado_em=DIA))
    _negocio(db_session, rep, _conta(db_session, "Ganha"), 1750.0, ganho_em=DIA)
    p = _painel(db_session, rep)
    funil = p["funil_mes"]
    assert (funil["reunioes"], funil["oportunidades_qualificadas"], funil["propostas"], funil["fechamentos"]) == (1, 2, 1, 1)
    assert p["fechado_crm_mrr"] == 1750.0 and p["realizado_new_mrr"] == 0  # ganho no CRM sem 1ª mensalidade ≠ New MRR
    semana = p["atividade"]["semana"]
    assert (semana["contas_trabalhadas"]["alvo"], semana["reunioes"]["realizado"], semana["new_mrr"] if "new_mrr" in semana else None) == (100, 1, None)
    assert p["atividade"]["dia"]["contas_trabalhadas"]["realizado"] == 0  # tudo foi ontem


def test_taxas_recalculadas_com_dados_reais_so_com_amostra_minima(db_session):
    rep = _rep(db_session)
    for i in range(25):
        conta = _conta(db_session, f"C{i}")
        _atividade(db_session, rep, conta, tipo="email")
        if i < 10:
            _atividade(db_session, rep, conta, tipo="ligacao")
    aprendizado = painel.calcular(db_session, [rep], "2026-10", HOJE)["aprendizado"]["por_representante"][rep.id]
    assert aprendizado["contato_efetivo"] == {"baseline": 0.30, "observada": 0.4, "amostra": 25, "recomendada": 0.4, "fonte": "OBSERVED"}
    assert aprendizado["reuniao"]["fonte"] == "BASELINE"  # 10 contatos < amostra mínima de 20: vale o baseline


# ---------------------------------------------------------------- mix e ticket

def test_mix_quality_indicador_sem_bloqueio(db_session):
    rep = _rep(db_session)
    predator = _plano(db_session, "PREDATOR", "modulo", ("predator",))
    _cliente(db_session, rep, "m1", 1000.0, datetime(2026, 10, 2), plano=predator)
    _cliente(db_session, rep, "m2", 500.0, datetime(2026, 10, 3), plano=_plano(db_session, "Bid Intelligence", "modulo", ("bids",)))
    p = _painel(db_session, rep)
    assert p["mix"]["por_familia"]["PREDATOR"]["valor"] == 1000.0 and p["mix"]["alto_valor_participacao"] == 0.3333
    assert p["mix"]["mix_quality"] == "LOW_TICKET_MIX" and p["ticket_medio"] == 750.0
    assert any(a["codigo"] == "LOW_TICKET_MIX" and a["severidade"] == "INFO" for a in p["alertas"])


# ---------------------------------------------------------------- comissão recorrente

def test_comissao_recorrente_por_competencia_cliente_e_status(db_session):
    rep = _rep(db_session)
    _cliente(db_session, rep, "r1", 1000.0, datetime(2026, 8, 5), pagamentos=(datetime(2026, 9, 5), datetime(2026, 10, 5)))
    _comissao(db_session, rep, "r1", 150.0, date(2026, 8, 5), "PAID")
    _comissao(db_session, rep, "r1", 150.0, date(2026, 9, 5), "PAID")
    _comissao(db_session, rep, "r1", 150.0, date(2026, 10, 5), "PAYABLE")
    _comissao(db_session, rep, "r1", 0.0, date(2026, 10, 6), "AWAITING_COST_PARAMETERS")
    comissao = _painel(db_session, rep)["comissao"]
    assert (comissao["realizada"], comissao["a_receber"], comissao["aguardando_parametros"], comissao["taxa"]) == (300.0, 150.0, 1, 0.20)
    assert comissao["por_competencia"] == {"2026-08": 150.0, "2026-09": 150.0, "2026-10": 150.0}


def test_inadimplencia_retem_comissao_e_repasse_respeita_politica(db_session):
    rep = _rep(db_session)
    _cliente(db_session, rep, "inad", 1000.0, datetime(2026, 7, 1))  # último pagamento há mais de 30 + 10 dias
    comissao = _comissao(db_session, rep, "inad", 200.0, date(2026, 7, 1), "PAYABLE")
    p = _painel(db_session, rep)
    assert (p["comissao"]["retida_inadimplencia"], p["comissao"]["a_receber"], p["carteira"]["DELINQUENT"]) == (200.0, 0.0, 1)
    db_session.commit()
    resultado = cron_repasse_comissoes_service.repassar_pendentes(db_session, FakePayoutProvider(), StubEmailProvider())
    assert resultado["retidas_inadimplencia"] == 1 and db_session.get(ComissaoRepresentante, comissao.id).status == "PAYABLE"
    regras = dict(configuracao.comissao_privada(db_session), inadimplencia={"ciclo_dias": 30, "tolerancia_dias": 10, "acao": "NONE"})
    configuracao.nova_politica(db_session, configuracao.CODIGO_POLITICA_COMISSAO_PRIVADA, regras, "Sem retenção", "gestor")
    assert _painel(db_session, rep)["comissao"]["a_receber"] == 200.0


def test_cancelamento_para_comissao_futura(db_session):
    rep = _rep(db_session)
    _cliente(db_session, rep, "canc", 1000.0, datetime(2026, 10, 1), ativa=False)
    p = _painel(db_session, rep)
    assert p["carteira"]["CANCELLED"] == 1
    with pytest.raises(ValidacaoFalhou, match="STOP_FUTURE"):
        regras = dict(configuracao.comissao_privada(db_session), cancelamento={"acao": "KEEP_PAYING"})
        configuracao.nova_politica(db_session, configuracao.CODIGO_POLITICA_COMISSAO_PRIVADA, regras, "x", "gestor")


# ---------------------------------------------------------------- campanha

REGRAS_CAMPANHA = configuracao.INICIAIS["CAMPAIGN:SUMMER_SALES_CHALLENGE_2026"]


@pytest.mark.parametrize(("mrr", "bonus"), [(20000.0, 0.0), (23000.0, 0.0), (27500.0, 0.20), (33000.0, 0.35), (41250.0, 0.50)])
def test_faixas_da_campanha(mrr, bonus):
    assert campanha.faixa(mrr / REGRAS_CAMPANHA["meta_individual"], REGRAS_CAMPANHA["faixas"])["bonus"] == bonus


def test_campanha_bonus_so_sobre_novas_vendas_e_com_elegibilidade(db_session):
    rep = _rep(db_session)
    _cliente(db_session, rep, "hist", 5000.0, datetime(2026, 6, 1), pagamentos=(datetime(2026, 12, 5), datetime(2027, 1, 5)))  # carteira histórica
    _comissao(db_session, rep, "hist", 1000.0, date(2026, 12, 5))
    _cliente(db_session, rep, "dez", 20000.0, datetime(2026, 12, 10), pagamentos=(datetime(2027, 1, 10),))
    _cliente(db_session, rep, "jan", 13000.0, datetime(2027, 1, 10))
    _comissao(db_session, rep, "dez", 400.0, date(2026, 12, 10))
    _comissao(db_session, rep, "jan", 260.0, date(2027, 1, 10))
    resultado = painel.calcular(db_session, [rep], "2027-01", date(2027, 2, 2))["campanhas"][0]
    linha = resultado["por_representante"][rep.id]
    assert (linha["new_mrr"], linha["attainment"], linha["faixa_bonus"]) == (33000.0, 1.2, 0.35)  # 120%
    assert linha["base_comissao_novas_vendas"] == 660.0  # a comissão da carteira histórica (1.000) fica fora
    assert (linha["elegivel"], linha["bonus"], linha["status_bonus"]) == (True, 231.0, "FINAL")
    assert resultado["equipe"]["meta"] == 27500.0  # meta individual × representantes ativos (1 aqui; 7 = R$ 192.500)


def test_campanha_sem_venda_em_um_mes_nao_paga_bonus(db_session):
    rep = _rep(db_session)
    _cliente(db_session, rep, "so-dez", 30000.0, datetime(2026, 12, 10))
    _comissao(db_session, rep, "so-dez", 600.0, date(2026, 12, 10))
    linha = painel.calcular(db_session, [rep], "2027-01", date(2027, 2, 2))["campanhas"][0]["por_representante"][rep.id]
    assert linha["faixa_bonus"] == 0.20 and not linha["elegivel"] and linha["bonus"] == 0.0
    assert "Sem venda nova em algum mês da campanha" in linha["motivos_inelegibilidade"]


# ---------------------------------------------------------------- governo

def test_governo_separado_do_new_mrr_privado(db_session):
    rep = _rep(db_session)
    gov = _plano(db_session, "Gov Dept", "governo", ("procurement",), segmento="GOVERNMENT")
    _cliente(db_session, rep, "prefeitura", 6000.0, datetime(2026, 10, 3), plano=gov)
    db_session.add_all([
        OportunidadeGoverno(titulo="Prefeitura X", entidade_governamental="X", estagio="PROPOSAL", representante_id=rep.id,
                            valor_estimado_licenca=Decimal("72000"), valor_estimado_assinatura=Decimal("24000"), criado_em=DIA,
                            data_prevista_fechamento=date(2027, 2, 1)),
        OportunidadeGoverno(titulo="Só identificada", entidade_governamental="Y", estagio="OPPORTUNITY_IDENTIFIED", representante_id=rep.id,
                            valor_estimado_licenca=Decimal("50000"), criado_em=DIA)])
    db_session.flush()
    p = _painel(db_session, rep)
    assert p["realizado_new_mrr"] == 0  # Government Booking nunca vira New MRR
    governo = p["governo"]
    assert (governo["qualificadas"], governo["pipeline_licenca"], governo["pipeline_assinatura_anual"]) == (1, 72000.0, 24000.0)
    assert (governo["novas_qualificadas_semana"], governo["meta_semana"]) == (1, 2)
    assert p["velocidade"]["STRATEGIC"]["pipeline_governo_tcv"] == 96000.0 and p["velocidade"]["STRATEGIC"]["pipeline_mrr"] == 0
    regras = dict(configuracao.performance(db_session), governo={**configuracao.performance(db_session)["governo"], "conta_na_quota_privada": True})
    with pytest.raises(ValidacaoFalhou, match="Governo|governamental"):
        configuracao.nova_politica(db_session, configuracao.CODIGO_POLITICA_PERFORMANCE, regras, "x", "gestor")


# ---------------------------------------------------------------- isolamento, permissões, daily

def test_isolamento_por_tenant_crm(db_session):
    rep = _rep(db_session)
    db_session.add(Tenant(id="outro-tenant", razao_social="Outro"))
    db_session.flush()
    conta_outro = _conta(db_session, "Fora", tenant="outro-tenant")
    _negocio(db_session, rep, conta_outro, 99999.0, tenant="outro-tenant")  # mesmo usuário, outro tenant: não entra
    _atividade(db_session, rep, conta_outro)
    p = _painel(db_session, rep)
    assert (p["pipeline"]["qualificado_mrr"], p["funil_mes"]["primeiros_toques"]) == (0, 0)


def test_permissoes_rep_ve_so_o_proprio_e_gestor_ve_equipe(client, db_session):
    ana, bia = _rep(db_session, "Ana"), _rep(db_session, "Bia")
    db_session.commit()
    usuario_ana = db_session.get(Usuario, ana.usuario_id)
    ok = client.get("/api/v1/map/performance/painel?competencia=2026-10&data_referencia=2026-10-15", headers=_headers(usuario_ana))
    assert ok.status_code == 200 and ok.json()["representante"]["id"] == ana.id
    assert client.get(f"/api/v1/map/performance/painel?representante_id={bia.id}", headers=_headers(usuario_ana)).status_code == 403
    for rota in ("equipe", "daily", "configuracao"):
        assert client.get(f"/api/v1/map/performance/{rota}", headers=_headers(usuario_ana)).status_code == 403
    estranho = Usuario(tenant_id="tenant-teste", nome="X", email="x@x.com", papel="admin", ativo=True)
    db_session.add(estranho)
    db_session.commit()
    assert client.get("/api/v1/map/performance/painel", headers=_headers(estranho)).status_code == 403
    equipe = client.get("/api/v1/map/performance/equipe?competencia=2026-10&data_referencia=2026-10-15").json()  # super_admin
    assert {linha["representante"]["id"] for linha in equipe["representantes"]} == {ana.id, bia.id}
    assert equipe["equipe"]["quota"] == 15000
    daily = client.get("/api/v1/map/performance/daily?competencia=2026-10&data_referencia=2026-10-15").json()
    assert {linha["representante"]["id"] for linha in daily["intervencoes"]} == {ana.id, bia.id}  # sem pipeline: risco de quota
    assert client.get("/api/v1/map/performance/acesso", headers=_headers(usuario_ana)).json() == {
        "gestor": False, "representante_id": ana.id, "pode_ver": True}


def test_configuracao_pela_api_versiona_e_vincula(client, db_session):
    rep = _rep(db_session, "Cid", com_usuario=False)
    usuario = Usuario(tenant_id=OPERADOR, nome="Cid", email="cid@cyberfort.com.br", papel="user", ativo=True)
    db_session.add(usuario)
    db_session.commit()
    assert client.put(f"/api/v1/map/performance/representantes/{rep.id}/usuario", json={"usuario_id": usuario.id}).json()["usuario_id"] == usuario.id
    resposta = client.post("/api/v1/map/performance/quotas", json={"representante_id": rep.id, "competencia": "2026-10", "valor": 8000,
                                                                   "motivo": "Carteira maior"})
    assert resposta.status_code == 201 and resposta.json()["versao"] == 1
    config = client.get("/api/v1/map/performance/configuracao").json()
    assert config["performance"]["regras"]["ticket_medio_baseline"] == 1750.0 and config["comissao_privada"]["regras"]["taxa"] == 0.20
    assert config["campanhas"][0]["regras"]["meta_individual"] == 27500.0
    invalida = client.post("/api/v1/map/performance/politicas", json={"codigo": "MAP_PERFORMANCE_POLICY", "regras": {}, "motivo": "x"})
    assert invalida.status_code == 422


def test_painel_com_representante_sem_vinculo_mostra_pendencia(db_session):
    rep = _rep(db_session, "Sem", com_usuario=False)
    p = _painel(db_session, rep)
    assert p["funil_mes"] is None and "Vincular o representante a um usuário do CRM" in p["pendencias"]
    with pytest.raises(NaoAutorizado):
        map_contract.performance.painel_equipe(db_session, Usuario(id=999, tenant_id="x", nome="n", email="e", papel="user"), "2026-10", HOJE)


# ---------------------------------------------------------------- eventos

def test_eventos_meeting_completed_e_proposal_sent(db_session):
    from app.services import proposta_service, reuniao_service

    db_session.add(Tenant(id="t-ev", razao_social="T"))
    db_session.flush()
    conta = _conta(db_session, "Ev", tenant="t-ev")
    reuniao = Reuniao(tenant_id="t-ev", conta_id=conta.id, decisor_id=1, vendedor_id="1", data_hora=DIA, status="agendada")
    db_session.add(reuniao)
    db_session.commit()
    reuniao_service.marcar_resultado(db_session, "t-ev", None, reuniao.id, "realizada")
    negocio = _negocio(db_session, Representante(usuario_id=None), conta, 100.0, tenant="t-ev")
    db_session.commit()
    proposta_service.anexar(db_session, "t-ev", None, negocio.id, "p.pdf", "application/pdf", b"%PDF")
    tipos = {e.tipo for e in db_session.query(EventoDominio).filter_by(tenant_id="t-ev").all()}
    assert {"MeetingCompleted", "ProposalSent"} <= tipos


# ---------------------------------------------------------------- desempenho

def _contar_consultas(db, funcao) -> int:
    contador = {"n": 0}

    def _antes(*_):
        contador["n"] += 1

    motor = db.get_bind()
    event.listen(motor, "before_cursor_execute", _antes)
    try:
        funcao()
    finally:
        event.remove(motor, "before_cursor_execute", _antes)
    return contador["n"]


def test_numero_de_consultas_nao_cresce_com_a_equipe(db_session):
    reps = [_rep(db_session, f"Q{i}") for i in range(7)]
    for i, rep in enumerate(reps):
        _cliente(db_session, rep, f"q{i}", 1000.0, datetime(2026, 10, 2))
        conta = _conta(db_session, f"QC{i}")
        _atividade(db_session, rep, conta)
        _negocio(db_session, rep, conta, 2000.0)
    painel.calcular(db_session, reps[:1], "2026-10", HOJE)  # aquece sementes de política/quota
    um = _contar_consultas(db_session, lambda: painel.calcular(db_session, reps[:1], "2026-10", HOJE))
    sete = _contar_consultas(db_session, lambda: painel.calcular(db_session, reps, "2026-10", HOJE))
    assert sete == um and um <= 45


# ---------------------------------------------------------------- D-081: time de tamanho variável e prontidão

@pytest.mark.parametrize("tamanho", [3, 9])
def test_equipe_e_campanha_acompanham_o_tamanho_do_time(db_session, tamanho):
    reps = [_rep(db_session, f"T{tamanho}x{i}") for i in range(tamanho)]
    dados = painel.calcular(db_session, reps, "2026-12", date(2026, 12, 15))
    assert dados["equipe"]["quota"] == 12500 * tamanho  # quota padrão vale para cada representante ativo
    assert dados["campanhas"][0]["equipe"]["meta"] == 27500.0 * tamanho  # sem meta de equipe fixa


def test_representante_novo_entra_e_inativo_sai_da_equipe(client, db_session):
    reps = [_rep(db_session, f"E{i}") for i in range(2)]
    db_session.commit()
    assert client.get("/api/v1/map/performance/equipe?competencia=2026-10&data_referencia=2026-10-15").json()["equipe"]["quota"] == 15000
    _rep(db_session, "Novo")
    reps[0].ativo = False
    db_session.commit()
    equipe = client.get("/api/v1/map/performance/equipe?competencia=2026-10&data_referencia=2026-10-15").json()
    assert {linha["representante"]["nome"] for linha in equipe["representantes"]} == {"E1", "Novo"}
    assert equipe["equipe"]["quota"] == 15000


def test_prontidao_lista_o_que_falta_e_fica_pronto(client, db_session):
    from app.models.oferta import Oferta

    sem = _rep(db_session, "Pendente", com_usuario=False)
    ligado = _rep(db_session, "Ligado")
    db_session.add_all([Oferta(tenant_id=OPERADOR, nome="B2B ON Suite", descricao="x"),
                        Oferta(tenant_id=OPERADOR, nome="PREDATOR", descricao="x"),
                        Oferta(tenant_id="tenant-teste", nome="Oferta de cliente", descricao="x")])
    db_session.commit()
    pronto = client.get("/api/v1/map/performance/configuracao").json()["prontidao"]
    assert (pronto["representantes_ativos"], pronto["vinculados"], pronto["pronto"]) == (2, 1, False)
    assert [r["nome"] for r in pronto["sem_vinculo"]] == ["Pendente"]
    assert {o["nome"] for o in pronto["ofertas"]} == {"B2B ON Suite", "PREDATOR"}  # só ofertas do CRM dos representantes
    assert "Confirmar o critério de contato efetivo" in pronto["pendencias"]
    assert "Confirmar o critério de contato efetivo" in client.get("/api/v1/map/performance/daily?data_referencia=2026-10-15").json()["configuracao_pendente"]

    candidatos = client.get("/api/v1/map/performance/usuarios-crm?busca=ligado").json()
    assert candidatos[0]["tenant_id"] == OPERADOR and candidatos[0]["vinculado_a"] == "Ligado"
    novo = Usuario(tenant_id=OPERADOR, nome="Pendente CRM", email="pendente@cyberfort.com.br", papel="user", ativo=True)
    db_session.add(novo)
    db_session.commit()
    client.put(f"/api/v1/map/performance/representantes/{sem.id}/usuario", json={"usuario_id": novo.id})

    ofertas = {o["nome"]: o["id"] for o in pronto["ofertas"]}
    cliente = db_session.query(Oferta).filter_by(tenant_id="tenant-teste").one()
    fora = client.put("/api/v1/map/performance/ofertas-familias", json={"familias": {str(cliente.id): "SUITE"}, "motivo": "x"})
    assert fora.status_code == 422  # oferta de outro tenant
    invalida = client.put("/api/v1/map/performance/ofertas-familias", json={"familias": {str(ofertas["PREDATOR"]): "XPTO"}, "motivo": "x"})
    assert invalida.status_code == 422
    client.put("/api/v1/map/performance/ofertas-familias", json={"familias": {str(ofertas["B2B ON Suite"]): "SUITE",
                                                                             str(ofertas["PREDATOR"]): "PREDATOR"}, "motivo": "Catálogo"})
    assert client.put("/api/v1/map/performance/contato-efetivo", json={"tipos": ["voo"], "motivo": "x"}).status_code == 422
    final = client.put("/api/v1/map/performance/contato-efetivo", json={"tipos": ["ligacao", "reuniao", "whatsapp"],
                                                                        "motivo": "Critério confirmado"}).json()
    assert (final["pronto"], final["pendencias"], final["tipos_contato_efetivo"]) == (True, [], ["ligacao", "reuniao", "whatsapp"])
    regras = configuracao.performance(db_session)
    assert regras["familia_por_oferta"] == {str(ofertas["B2B ON Suite"]): "SUITE", str(ofertas["PREDATOR"]): "PREDATOR"}
    assert ligado.id  # o vínculo existente não muda


def test_configuracao_guiada_so_para_o_gestor(client, db_session):
    rep = _rep(db_session, "Rep")
    db_session.commit()
    headers = _headers(db_session.get(Usuario, rep.usuario_id))
    assert client.get("/api/v1/map/performance/usuarios-crm?busca=re", headers=headers).status_code == 403
    assert client.put("/api/v1/map/performance/contato-efetivo", json={"tipos": ["ligacao"], "motivo": "x"}, headers=headers).status_code == 403
    assert client.put("/api/v1/map/performance/ofertas-familias", json={"familias": {}, "motivo": "x"}, headers=headers).status_code == 403
