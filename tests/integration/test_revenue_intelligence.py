"""Analytics & Revenue Intelligence (Fase 16).

Cada métrica é conferida contra um cenário montado à mão, com o valor
exato esperado. Também: isolamento entre tenants, barreira Buy/Sell
(lado comprador nunca aparece na receita) e gate por módulo.
"""

from datetime import UTC, date, datetime, timedelta

from app.api.deps import get_plan_limits_provider
from app.main import app
from app.models.alerta_detrator import AlertaDetrator
from app.models.conta import Conta
from app.models.contrato_compra import ContratoCompra
from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.decisor import Decisor
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.fornecedor_compras import FornecedorCompras
from app.models.item_pca import ItemPca
from app.models.oferta import Oferta
from app.models.orgao_publico import OrgaoPublico
from app.models.plano_contratacao import PlanoContratacao
from app.models.processo_contratacao import ProcessoContratacao
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.sala_compra import SalaCompra
from app.models.sala_corporativa import SalaCorporativa
from app.models.sinal_oportunidade import SinalOportunidade
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import crm_service

TENANT = "tenant-teste"
R = "/api/v1/inteligencia/receita/metricas"
P = "/api/v1/procurement/metricas"
AGORA = datetime.now(UTC).replace(tzinfo=None)


def _conta(db, nome, tenant=TENANT, **campos) -> Conta:
    conta = Conta(tenant_id=tenant, nome=nome, status="prospectada", **campos)
    db.add(conta)
    db.commit()
    db.add(Decisor(tenant_id=tenant, conta_id=conta.id, nome=f"Decisor {nome}"))
    db.commit()
    return conta


def _negocio(db, conta, valor, tipo="aberto", tenant=TENANT, **campos):
    estagios = {e.tipo: e for e in crm_service.garantir_estagios_padrao(db, tenant)}
    decisor = db.query(Decisor).filter_by(conta_id=conta.id).first()
    negocio = crm_service.criar_negocio(db, tenant, None, conta.id, decisor.id, f"N {conta.nome} {valor}", valor=valor)
    if tipo != "aberto":
        crm_service.mover_estagio(db, tenant, None, negocio.id, estagios[tipo].id, motivo_perda="Preço" if tipo == "perdido" else None)
    for chave, valor_campo in campos.items():
        setattr(negocio, chave, valor_campo)
    db.commit()
    return negocio


def _ia(db, entidade_tipo, entidade_id, feature="crm.teste", tenant=TENANT):
    db.add(RegistroUsoIa(tenant_id=tenant, agente="teste", feature=feature, modulo="crm", status="sucesso", tokens_entrada=1,
                         tokens_saida=1, latencia_ms=1, entidade_tipo=entidade_tipo, entidade_id=entidade_id))
    db.commit()


def _sinal(db, tipo, status="novo", negocio=None, conta=None, tenant=TENANT):
    alvo = f"tenant-alvo-{db.query(SinalOportunidade).count()}"  # um sinal por (alvo, tipo)
    db.add(SinalOportunidade(tenant_id=tenant, tenant_id_alvo=alvo, tipo_sinal=tipo, score=0.8, confianca="alta",
                             motivo="teste", evidencias=[], status=status, negocio_id_gerado=negocio.id if negocio else None,
                             conta_id_gerada=conta.id if conta else None))
    db.commit()


def _cenario_vendas(db):
    rede = _conta(db, "Rede", origem="rede_social_signal")
    _negocio(db, rede, 1000)  # originado: conta nascida de sinal
    via_sinal = _negocio(db, _conta(db, "Via sinal"), 2000)  # originado: sinal convertido
    _sinal(db, "intent_compativel", "convertido", negocio=via_sinal)

    com_sala = _negocio(db, _conta(db, "Sala"), 3000)  # influenciado: sala de compra
    sala = SalaCorporativa(tenant_id_a=TENANT, tenant_id_b="tenant-alvo")
    db.add(sala)
    db.commit()
    db.add(SalaCompra(sala_corporativa_id=sala.id, tenant_id_vendedor=TENANT, negocio_id=com_sala.id, visivel_para_comprador=True))
    tocada = _conta(db, "Tocada")
    _negocio(db, tocada, 3500)  # influenciado: conta que recebeu sinal depois
    _sinal(db, "fit_icp", "aceita", conta=tocada)

    com_ia = _conta(db, "Com IA")
    _ia(db, "conta", com_ia.id)
    _negocio(db, com_ia, 4000)  # assistido por IA (aberto)
    _negocio(db, com_ia, 500, tipo="ganho")  # receita assistida por IA

    oferta = Oferta(tenant_id=TENANT, nome="Licenças", descricao="x")
    db.add(oferta)
    db.commit()
    sem_toque = _conta(db, "Sem toque")
    ganho_sem_toque = _negocio(db, sem_toque, 700, tipo="ganho", oferta_id=oferta.id)
    _negocio(db, sem_toque, 300, tipo="perdido", oferta_id=oferta.id)
    _sinal(db, "match_intent", "convertido", negocio=ganho_sem_toque)
    _sinal(db, "fit_icp")

    resgatada = _conta(db, "Resgatada", cliente_desde=AGORA - timedelta(days=400))
    _ia(db, "conta", resgatada.id, feature="map.script_resgate_conta")
    _negocio(db, resgatada, 900, tipo="ganho")
    perdida = _conta(db, "Perdida", cliente_desde=AGORA - timedelta(days=400), cliente_cancelado_em=AGORA)
    db.add(AlertaDetrator(tenant_id=TENANT, pesquisa_nps_id=1, conta_id=perdida.id, decisor_id=1, nota=2, sugestao_acao="ligar"))
    db.commit()

    # outro tenant: nada disto pode aparecer
    alheia = _conta(db, "Alheia", tenant="tenant-alheio", origem="rede_social_signal")
    _negocio(db, alheia, 99999, tenant="tenant-alheio")


def test_metricas_de_receita_batem_com_o_cenario(client, db_session):
    _cenario_vendas(db_session)
    m = client.get(R).json()

    assert (m["network_sourced_pipeline"]["valor"], m["network_sourced_pipeline"]["negocios"]) == (3000.0, 2)
    assert (m["network_influenced_pipeline"]["valor"], m["network_influenced_pipeline"]["negocios"]) == (6500.0, 2)
    assert m["ai_assisted_pipeline"]["valor"] == 4000.0
    assert (m["ai_assisted_revenue"]["valor"], m["ai_assisted_revenue"]["negocios"]) == (1400.0, 2)  # 500 + 900 (resgate é IA na conta)

    sinais = m["signal_conversion"]
    assert (sinais["gerados"], sinais["convertidos"], sinais["valor"], sinais["convertidos_em_ganho"]) == (4, 2, 0.5, 1)
    assert sinais["por_tipo"]["fit_icp"] == {"gerados": 2, "convertidos": 0, "taxa": 0.0}
    assert (m["intent_conversion"]["valor"], m["intent_conversion"]["amostra"]) == (1.0, 1)
    assert (m["match_conversion"]["valor"], m["match_conversion"]["amostra"]) == (0.3333, 3)

    ofertas = {o["oferta"]: o for o in m["offer_conversion"]["por_oferta"]}
    assert (ofertas["Licenças"]["ganhos"], ofertas["Licenças"]["perdidos"], ofertas["Licenças"]["taxa_ganho"]) == (1, 1, 0.5)
    assert ofertas["Licenças"]["valor_ganho"] == 700.0

    churn = m["churn_prevention_value"]
    assert (churn["valor"], churn["clientes_em_risco_com_acao"], churn["clientes_retidos"], churn["taxa_retencao"]) == (900.0, 2, 1, 0.5)

    for chave, item in m.items():
        if chave != "periodo":
            assert item["metodologia"] and "amostra" in item, chave
    assert "99999" not in str(m)


def test_sem_dados_as_taxas_sao_nulas_e_nao_zero(client):
    m = client.get(R).json()
    assert m["signal_conversion"]["valor"] is None and m["offer_conversion"]["valor"] is None
    assert m["churn_prevention_value"]["taxa_retencao"] is None
    assert m["network_sourced_pipeline"]["valor"] == 0.0 and m["network_sourced_pipeline"]["amostra"] == 0


def test_janela_de_tempo_filtra_fluxos_e_valida_ordem(client, db_session):
    _cenario_vendas(db_session)
    futuro = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    m = client.get(R, params={"inicio": futuro, "fim": (datetime.now(UTC) + timedelta(days=60)).isoformat()}).json()
    assert m["ai_assisted_revenue"]["valor"] == 0.0 and m["signal_conversion"]["gerados"] == 0
    assert m["network_sourced_pipeline"]["valor"] == 3000.0  # pipeline aberto é retrato de agora
    assert client.get(R, params={"inicio": futuro, "fim": futuro}).status_code == 422


def test_risco_de_renovacao_de_contratos_publicos_so_com_bid_intelligence(client, db_session, monkeypatch):
    hoje = date.today()
    db_session.add_all([
        ContratoVendaPublica(tenant_id=TENANT, objeto="Suporte", valor=10000, vigencia_fim=hoje + timedelta(days=30), renovavel=False, status="VIGENTE"),
        ContratoVendaPublica(tenant_id=TENANT, objeto="Licenças", valor=5000, vigencia_fim=hoje + timedelta(days=90), renovavel=True, status="VIGENTE"),
        ContratoVendaPublica(tenant_id=TENANT, objeto="Longo", valor=7000, vigencia_fim=hoje + timedelta(days=300), renovavel=True, status="VIGENTE"),
        ContratoVendaPublica(tenant_id=TENANT, objeto="Sem fim", valor=1, vigencia_fim=None, renovavel=True, status="VIGENTE"),
    ])
    db_session.commit()
    risco = client.get(R).json()["contract_renewal_risk"]
    assert (risco["valor"], risco["vencendo"], risco["nao_renovaveis"], risco["valor_nao_renovavel"], risco["sem_data_de_fim"]) == (
        15000.0, 2, 1, 10000.0, 1)

    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"bids"}}))
    assert "contract_renewal_risk" not in client.get(R).json()
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"crm"}}))
    assert client.get(R).status_code == 403


# --- Lado comprador --------------------------------------------------------------------


def _cenario_compras(db):
    hoje = date.today()
    orgao = OrgaoPublico(tenant_id=TENANT, nome="Prefeitura")
    db.add(orgao)
    db.commit()
    plano = PlanoContratacao(tenant_id=TENANT, orgao_id=orgao.id, ano=hoje.year, nome="PCA", status="EM_EXECUCAO")
    db.add(plano)
    db.commit()
    item_ok = ItemPca(tenant_id=TENANT, plano_id=plano.id, descricao="Notebooks", valor_estimado=100.0, status="CONTRATADO")
    item_pendente = ItemPca(tenant_id=TENANT, plano_id=plano.id, descricao="Cadeiras", valor_estimado=100.0, status="PLANEJADO")
    db.add_all([item_ok, item_pendente])
    db.commit()
    fornecedor = FornecedorCompras(tenant_id=TENANT, razao_social="Fornecedor Sigiloso Ltda")
    db.add(fornecedor)
    db.commit()
    concluido = ProcessoContratacao(tenant_id=TENANT, orgao_id=orgao.id, item_pca_id=item_ok.id, objeto="Notebooks", status="CONTRATADO",
                                    categoria="TI", criado_em=AGORA - timedelta(days=30))
    andamento = ProcessoContratacao(tenant_id=TENANT, orgao_id=orgao.id, objeto="Limpeza nova", status="EM_ANDAMENTO",
                                    categoria="LIMPEZA", criado_em=AGORA - timedelta(days=10))
    db.add_all([concluido, andamento])
    db.commit()
    contrato = ContratoCompra(tenant_id=TENANT, orgao_id=orgao.id, processo_id=concluido.id, fornecedor_id=fornecedor.id, objeto="Notebooks",
                              categoria="TI", valor_inicial=80.0, valor_atual=100.0, status="VIGENTE", necessidade_continuada=True,
                              vigencia_fim=hoje + timedelta(days=30), criado_em=AGORA)
    limpeza = ContratoCompra(tenant_id=TENANT, orgao_id=orgao.id, fornecedor_id=fornecedor.id, objeto="Limpeza", categoria="LIMPEZA",
                             valor_atual=50.0, status="VIGENTE", necessidade_continuada=True, vigencia_fim=hoje + timedelta(days=20))
    db.add_all([contrato, limpeza])
    db.commit()
    db.add_all([
        EventoContratoCompra(tenant_id=TENANT, fornecedor_id=fornecedor.id, contrato_id=contrato.id, tipo="FISCALIZACAO", nota=4.0),
        EventoContratoCompra(tenant_id=TENANT, fornecedor_id=fornecedor.id, contrato_id=contrato.id, tipo="FISCALIZACAO", nota=5.0),
        EventoContratoCompra(tenant_id=TENANT, fornecedor_id=fornecedor.id, contrato_id=contrato.id, tipo="OCORRENCIA"),
    ])
    db.commit()


def test_metricas_de_compras_batem_com_o_cenario(client, db_session):
    _cenario_compras(db_session)
    m = client.get(P).json()
    ciclo = m["procurement_cycle_time"]
    assert (ciclo["valor"], ciclo["concluidos"], ciclo["em_andamento"], ciclo["idade_mediana_em_andamento"]) == (30, 1, 1, 10)
    pca = m["pca_execution"]["por_plano"][0]
    assert (m["pca_execution"]["valor"], pca["execucao_itens"], pca["valor_contratado"]) == (0.5, 0.5, 100.0)
    fornecedor = m["supplier_performance"]["por_fornecedor"][0]
    assert (m["supplier_performance"]["valor"], fornecedor["ocorrencias"], fornecedor["acrescimo_medio"]) == (4.5, 1, 0.25)
    renovacao = {c["objeto"]: c for c in m["contract_renewal_risk"]["contratos"]}
    assert renovacao["Notebooks"]["risco"] == "ALTO"  # continuado, 30 dias, sem processo sucessor
    assert renovacao["Limpeza"]["risco"] == "BAIXO" and renovacao["Limpeza"]["processo_sucessor_em_andamento"]
    assert m["contract_renewal_risk"]["valor"] == 1


def test_barreira_buy_sell_nas_metricas(client, db_session, monkeypatch):
    _cenario_compras(db_session)
    _cenario_vendas(db_session)
    receita = client.get(R).text
    assert "Fornecedor Sigiloso" not in receita and "Notebooks" not in receita and "procurement" not in receita
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"procurement"}}))
    assert client.get(P).status_code == 403
    assert client.get(R).status_code == 200


def test_metricas_de_compras_isoladas_por_tenant(client, db_session, criar_usuario_autenticado):
    _cenario_compras(db_session)
    outro = criar_usuario_autenticado("tenant-outro-metricas", papel="admin", email="admin@outro-metricas.com")
    m = client.get(P, headers=outro).json()
    assert m["procurement_cycle_time"]["amostra"] == 0 and m["supplier_performance"]["por_fornecedor"] == []
    assert m["pca_execution"]["valor"] is None
