"""Matriz de franquias de enriquecimento por plano, pacotes adicionais, POC, Enterprise e rotinas mensais.

Cobre: limites por plano (inclui Teste gratuito = 3 decisores), concessão mensal idempotente no mês de Brasília, expiração sem acúmulo, pacotes (preço
exato em centavos, expiração informada antes da compra, saldo separado que não aumenta limites, >3.000 sem checkout), rentabilidade, POC com teto
calculado, limites por período do Enterprise, ICP grande sem limite, site fora da franquia Lusha, webhook de pagamento e permissões.
Provedor e pagamento sempre simulados: nenhuma chamada real, nenhum orçamento real."""

import hashlib
import hmac
from datetime import datetime
from decimal import Decimal

import pytest

from app.api.deps import get_contact_enrichment_provider, get_fiscal_provider, get_payment_provider
from app.contexts.enriquecimento import config, custo, ledger, matriz, pacotes, poc, precos, renovacao
from app.contexts.enriquecimento.matriz_dados import PACOTES, PLANOS
from app.core.config import settings
from app.main import app
from app.models.conta import Conta
from app.models.creditos_ia import ExecucaoIa
from app.models.enriquecimento_creditos import EnriquecimentoCompra, EnriquecimentoMovimento, PesquisaDecisores
from app.models.plano import Plano
from app.providers.fiscal.stub import StubFiscalProvider
from app.providers.payment.stub import StubPaymentProvider
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services.errors import NaoAutorizado, PesquisaBloqueada, ValidacaoFalhou
from tests.integration.test_pesquisa_decisores_governanca import (
    A,
    ADMIN,
    URL,
    B,
    ProvedorPago,
    cenario,
    confirmar,
    contas,
    esperar_bloqueio,
    erro_seguro,
    eu,
    invariantes,
    plano_id,
    preparar_tenant_b,
    previa,
    rodar,
    tipos,
)

AGORA = datetime(2026, 10, 15, 15, 0)  # 12:00 em Brasília
FISCAL = StubFiscalProvider()


@pytest.fixture()
def prov_api(client):
    """O provedor que as rotas HTTP enxergam (a fixture `client` injeta um fake sem custo por padrão)."""
    provedor = ProvedorPago()
    app.dependency_overrides[get_contact_enrichment_provider] = lambda: provedor
    return provedor


def aplicar_linha(db, linha):
    """Aplica uma linha da matriz ao plano do tenant de teste (mapeamento explícito do administrador)."""
    return matriz.aplicar(db, ator_id="1", tenant_auditoria=A, mapeamento={linha: plano_id(db)})


def catalogo(db):
    for codigo, nome, creditos, unitario, total, status, ordem in PACOTES:
        pacotes.definir_pacote(db, codigo=codigo, nome=nome, quantidade_creditos=creditos, preco_unitario_brl=unitario, preco_total_brl=total, status=status,
                               ordem=ordem, ator_id="1", tenant_auditoria=A, motivo="catálogo de teste", aprovar=True)


def dados_fiscais(db, tenant_id, cnpj="11222333000181"):
    from app.models.tenant import Tenant

    tenant = db.get(Tenant, tenant_id)
    tenant.cnpj = cnpj
    db.commit()


def liberar_lusha(db, linha="Starter"):
    """Plano com a franquia da matriz + política e orçamento aprovados: a pesquisa (e a compra de créditos) fica liberada."""
    cenario(db, padrao=None)
    aplicar_linha(db, linha)
    dados_fiscais(db, A)


def pagar(db, pagamento: StubPaymentProvider, compra, valor=None, status="approved", agora=AGORA):
    pagamento_id = pagamento.aprovar(compra.preferencia_id_externo)
    if valor is not None:
        pagamento._preferencias[compra.preferencia_id_externo]["valor"] = valor
    pagamento._preferencias[compra.preferencia_id_externo]["status"] = status
    return pagamento_id, pacotes.confirmar_via_webhook(db, pagamento, pagamento_id, agora)


# ============================================================ a matriz do PO: limites por plano ======================================


@pytest.mark.parametrize("linha,franquia,decisores", [("Teste gratuito", 30, 3), ("Starter", 30, 5), ("Professional", 60, 10), ("Business", 120, 20),
                                                       ("Corporate", 180, 30)])
def test_cada_linha_da_matriz_vira_a_configuracao_aprovada_do_plano(client, db_session, linha, franquia, decisores):
    cenario(db_session)
    relatorio = aplicar_linha(db_session, linha)
    assert [a["plano"] for a in relatorio["aplicados"]] == ["Plano Padrão Teste"]
    cfg, motivo = config.config_vigente(db_session, A)
    assert motivo is None and cfg.origem == "plano" and cfg.modo == "franquia_fixa" and cfg.utilizavel
    assert (cfg.franquia_creditos, cfg.periodicidade, cfg.limite_creditos_pesquisa, cfg.decisores_por_empresa_max) == (franquia, "mensal", franquia, decisores)


def test_configuracao_anterior_com_5_decisores_e_substituida_pelo_teto_do_teste_gratuito(client, db_session):
    cenario(db_session, padrao=5, maximo=5)  # configuração antiga: padrão e teto de 5 decisores
    relatorio = aplicar_linha(db_session, "Teste gratuito")
    assert relatorio["ajustes"] == [{"plano": "Plano Padrão Teste", "campo": "decisores_por_empresa_padrao", "de": 5, "para": None}]
    cfg, _ = config.config_vigente(db_session, A)
    assert cfg.decisores_por_empresa_max == 3 and cfg.decisores_por_empresa_padrao is None
    with pytest.raises(ValidacaoFalhou, match="excede o máximo"):
        previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=5)


def test_teste_gratuito_permite_no_maximo_3_decisores_nunca_5(client, db_session):
    liberar_lusha(db_session, "Teste gratuito")
    solic, prov = eu(db_session), ProvedorPago()
    cs = contas(db_session, 2)
    with pytest.raises(ValidacaoFalhou, match=r"excede o máximo do seu plano \(3\)"):
        previa(db_session, solic, cs, prov, d=5)
    with pytest.raises(ValidacaoFalhou, match="Informe quantos decisores"):
        previa(db_session, solic, cs, prov)  # sem padrão: nada é escolhido em silêncio
    p = previa(db_session, solic, cs, prov, d=3)
    assert p.decisores_por_empresa == 3 and p.estimativa["limites"]["decisores_por_empresa_max"] == 3 and p.estimativa["viavel"] is True


def test_nenhuma_configuracao_do_projeto_permite_5_decisores_no_teste_gratuito():
    linha = PLANOS["Teste gratuito"]["config"]
    assert linha["decisores_por_empresa_max"] == 3 and linha["franquia_creditos"] == 30 and linha["limite_creditos_pesquisa"] == 30


def test_creditos_por_pesquisa_sao_limitados_pela_franquia_e_o_bloqueio_mostra_alternativas_sem_mudar_a_selecao(client, db_session):
    liberar_lusha(db_session, "Starter")  # 30 créditos por pesquisa, até 5 decisores por empresa
    solic, prov = eu(db_session), ProvedorPago()
    cabe = previa(db_session, solic, contas(db_session, 6), prov, d=5)  # 6 × 5 = 30
    assert cabe.estimativa["viavel"] is True and cabe.estimativa["creditos_maximos"] == 30
    nao_cabe = previa(db_session, solic, contas(db_session, 7), prov, d=5)  # 7 × 5 = 35 > 30
    assert nao_cabe.estimativa["viavel"] is False
    assert nao_cabe.estimativa["bloqueios"][0]["codigo"] == "limite_por_pesquisa"
    assert nao_cabe.decisores_por_empresa == 5 and nao_cabe.total_empresas == 7  # a seleção não foi alterada
    tipos_ajuste = {a["tipo"] for a in nao_cabe.estimativa["ajustes_sugeridos"]}
    assert tipos_ajuste  # alternativas (menos decisores por empresa ou menos empresas), só sugeridas
    esperar_bloqueio("limite_por_pesquisa", lambda: confirmar(db_session, solic, nao_cabe, prov))
    assert ledger.reservado(db_session, A) == 0 and prov.chamadas == []


def test_aplicar_a_matriz_e_idempotente_versionada_e_nao_cria_planos(client, db_session):
    cenario(db_session)
    primeira = aplicar_linha(db_session, "Professional")
    assert primeira["aplicados"][0]["versao"] == 2  # a v1 era a do cenário de teste; a matriz entra como nova versão aprovada
    outra = aplicar_linha(db_session, "Professional")
    assert outra["aplicados"] == [] and outra["inalterados"] == ["Plano Padrão Teste"]  # reaplicar não cria versão
    assert "Business" in outra["nao_encontrados"] and "Corporate" in outra["nao_encontrados"]  # planos que não existem não são inventados
    assert db_session.query(Plano).filter(Plano.nome.in_(["Business", "Corporate", "Starter"])).count() == 0
    assert any(s["situacao"] == "aplicada" for s in matriz.status(db_session, {"Professional": plano_id(db_session)}))
    aplicar_linha(db_session, "Corporate")
    assert [s["situacao"] for s in matriz.status(db_session, {"Professional": plano_id(db_session)}) if s["matriz"] == "Professional"] == ["diverge_da_matriz"]


def test_planos_pelo_nome_exato_sao_encontrados_sem_mapeamento(client, db_session):
    for nome in ("Teste", "Starter"):
        db_session.add(Plano(nome=nome, franquia_contas_mes=10, max_usuarios=5, preco_mensal=0.0))
    db_session.commit()
    relatorio = matriz.aplicar(db_session, ator_id="1", tenant_auditoria=A)
    assert sorted(a["plano"] for a in relatorio["aplicados"]) == ["Starter", "Teste"]
    assert "POC" in relatorio["nao_encontrados"] and "Enterprise" in relatorio["nao_encontrados"]


def test_linha_inexistente_no_mapeamento_e_recusada(client, db_session):
    with pytest.raises(Exception, match="não existe"):
        matriz.aplicar(db_session, ator_id="1", tenant_auditoria=A, mapeamento={"Starter": 99999})


# ============================================================ franquia mensal: concessão, expiração, não acúmulo ======================


def test_concessao_mensal_e_idempotente_e_o_ciclo_vira_no_mes_de_brasilia(client, db_session):
    liberar_lusha(db_session, "Starter")
    cfg, _ = config.config_vigente(db_session, A)
    for _ in range(3):  # reprocessar a renovação no mesmo ciclo não duplica
        ledger.preparar(db_session, A, cfg, AGORA)
        db_session.commit()
    assert tipos(db_session) == ["CONCESSAO"] and ledger.saldo(db_session, A) == 30
    # 31/10 23:59 em Brasília (= 01/11 02:59 UTC) ainda é outubro; 01/11 00:00 em Brasília (= 03:00 UTC) já é novembro
    ledger.preparar(db_session, A, cfg, datetime(2026, 11, 1, 2, 59))
    db_session.commit()
    assert tipos(db_session) == ["CONCESSAO"]
    ledger.preparar(db_session, A, cfg, datetime(2026, 11, 1, 3, 0))
    db_session.commit()
    assert tipos(db_session) == ["CONCESSAO", "EXPIRACAO", "RENOVACAO"]
    assert ledger.saldo(db_session, A) == 30  # não acumula: os 30 de outubro venceram, os 30 de novembro entraram
    invariantes(db_session)


def test_o_que_foi_consumido_no_mes_nao_expira_so_o_resto(client, db_session):
    liberar_lusha(db_session, "Starter")
    cfg, _ = config.config_vigente(db_session, A)
    ledger.preparar(db_session, A, cfg, AGORA)
    ledger.travar_carteira(db_session, A)
    ledger.lancar(db_session, A, "CONSUMO", delta_saldo=-10, agora=AGORA)
    db_session.commit()
    ledger.preparar(db_session, A, cfg, datetime(2026, 11, 2, 12, 0))
    db_session.commit()
    expirado = db_session.query(EnriquecimentoMovimento).filter_by(tenant_id=A, tipo="EXPIRACAO").one()
    assert expirado.delta_saldo == -20 and ledger.saldo(db_session, A) == 30


def test_a_rotina_mensal_renova_e_expira_de_forma_idempotente_e_isolada_por_tenant(client, db_session):
    liberar_lusha(db_session, "Starter")
    primeiro = renovacao.renovar_todos(db_session, AGORA)
    assert primeiro["franquias_concedidas"] == 1 and primeiro["erros"] == 0
    de_novo = renovacao.renovar_todos(db_session, AGORA)
    assert de_novo["franquias_concedidas"] == 0 and tipos(db_session) == ["CONCESSAO"]
    virada = renovacao.renovar_todos(db_session, datetime(2026, 11, 3, 12, 0))
    assert virada["franquias_concedidas"] == 1 and virada["creditos_expirados"] == 30
    assert renovacao.renovar_todos(db_session, datetime(2026, 11, 3, 12, 0))["creditos_expirados"] == 0
    assert ledger.saldo(db_session, A) == 30


# ============================================================ pacotes adicionais ======================================================


def test_catalogo_traz_os_precos_exatos_e_o_pacote_acima_de_3000_nao_tem_preco_nem_checkout(client, db_session):
    catalogo(db_session)
    vitrine = pacotes.catalogo(db_session, AGORA)
    por_codigo = {p["codigo"]: p for p in vitrine["pacotes"]}
    assert [(c, por_codigo[c]["preco_unitario_brl"], por_codigo[c]["preco_total_brl"]) for c in ("ENRIQ_400", "ENRIQ_660", "ENRIQ_1200", "ENRIQ_3000")] == [
        ("ENRIQ_400", "1.35", "540.00"), ("ENRIQ_660", "1.28", "844.80"), ("ENRIQ_1200", "1.21", "1452.00"), ("ENRIQ_3000", "1.08", "3240.00")]
    sob = por_codigo["ENRIQ_ACIMA_3000"]
    assert sob["sob_negociacao"] is True and sob["checkout_automatico"] is False and sob["preco_total_brl"] is None and sob["preco_unitario_brl"] is None
    assert vitrine["regras"] == {"saldo_separado_da_franquia": True, "aumenta_limites_do_plano": False, "expira_no_fim_do_mes": True, "acumula": False}
    assert vitrine["expira_em_previsto"] == "2026-11-01T03:00:00"  # fim de outubro em Brasília


@pytest.mark.parametrize("creditos,unitario,total", [(400, "1.35", "540.00"), (660, "1.28", "844.80"), (1200, "1.21", "1452.00"), (3000, "1.08", "3240.00")])
def test_total_do_pacote_e_creditos_vezes_unitario_em_decimal_exato(creditos, unitario, total):
    assert precos.centavos(Decimal(creditos) * Decimal(unitario)) == Decimal(total)


def test_definir_pacote_recusa_total_incoerente_preco_em_pacote_negociado_e_valores_invalidos(client, db_session):
    base = dict(ator_id="1", tenant_auditoria=A, motivo="teste")
    with pytest.raises(ValidacaoFalhou, match="não confere"):
        pacotes.definir_pacote(db_session, codigo="ENRIQ_X", nome="X", quantidade_creditos=400, preco_unitario_brl="1.35", preco_total_brl="539.99", **base)
    with pytest.raises(ValidacaoFalhou, match="sob negociação"):
        pacotes.definir_pacote(db_session, codigo="ENRIQ_Y", nome="Y", quantidade_creditos=4000, preco_unitario_brl="1.00", status="CONTACT_SALES", **base)
    with pytest.raises(ValidacaoFalhou):
        pacotes.definir_pacote(db_session, codigo="ENRIQ_Z", nome="Z", quantidade_creditos=0, preco_unitario_brl="1.00", **base)
    with pytest.raises(ValidacaoFalhou):
        pacotes.definir_pacote(db_session, codigo="ENRIQ_W", nome="W", quantidade_creditos=10, preco_unitario_brl="-1", **base)
    assert pacotes.pacotes_vigentes(db_session) == []  # nada pendente vale; nada inválido foi gravado


def test_pacote_novo_nasce_pendente_e_a_versao_aprovada_continua_valendo_ate_aprovar(client, db_session):
    catalogo(db_session)
    nova = pacotes.definir_pacote(db_session, codigo="ENRIQ_400", nome="400 créditos", quantidade_creditos=400, preco_unitario_brl="1.40",
                                  ator_id="1", tenant_auditoria=A, motivo="reajuste")
    vigente = {p.codigo: p for p in pacotes.pacotes_vigentes(db_session)}["ENRIQ_400"]
    assert vigente.versao == 1 and Decimal(str(vigente.preco_total_brl)) == Decimal("540.00")
    pacotes.aprovar_pacote(db_session, nova.id, "1", A)
    vigente = {p.codigo: p for p in pacotes.pacotes_vigentes(db_session)}["ENRIQ_400"]
    assert vigente.versao == 2 and Decimal(str(vigente.preco_total_brl)) == Decimal("560.00")


def test_compra_exige_aceite_da_expiracao_e_pacote_negociado_nao_tem_checkout(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    pagamento, prov = StubPaymentProvider(), ProvedorPago()
    base = dict(payment_provider=pagamento, email_pagador="a@b.com", provider=prov, fiscal=FISCAL, ator_id="1", agora=AGORA)
    with pytest.raises(ValidacaoFalhou, match="expiram no fim do mês"):
        pacotes.iniciar_compra(db_session, A, "ENRIQ_400", aceite_expiracao=False, **base)
    with pytest.raises(ValidacaoFalhou, match="negociado com o comercial"):
        pacotes.iniciar_compra(db_session, A, "ENRIQ_ACIMA_3000", aceite_expiracao=True, **base)
    assert db_session.query(EnriquecimentoCompra).count() == 0 and pagamento._preferencias == {}


def test_compra_e_bloqueada_enquanto_a_pesquisa_lusha_esta_indisponivel(client, db_session):
    catalogo(db_session)  # sem plano, política nem orçamento aprovados
    pagamento = StubPaymentProvider()
    erro = pytest.raises(PesquisaBloqueada, pacotes.iniciar_compra, db_session, A, "ENRIQ_400", aceite_expiracao=True, payment_provider=pagamento,
                         email_pagador="a@b.com", provider=ProvedorPago(), fiscal=FISCAL, ator_id="1", agora=AGORA)
    assert erro.value.bloqueios and pagamento._preferencias == {} and db_session.query(EnriquecimentoCompra).count() == 0


def test_compra_aprovada_pelo_webhook_vira_saldo_adicional_separado_que_nao_muda_nenhum_limite(client, db_session):
    liberar_lusha(db_session, "Starter")
    catalogo(db_session)
    pagamento, prov = StubPaymentProvider(), ProvedorPago()
    cfg_antes, _ = config.config_vigente(db_session, A)
    ledger.preparar(db_session, A, cfg_antes, AGORA)
    compra = pacotes.iniciar_compra(db_session, A, "ENRIQ_660", aceite_expiracao=True, payment_provider=pagamento, email_pagador="a@b.com", provider=prov, fiscal=FISCAL,
                                    ator_id="1", agora=AGORA)
    assert compra.status == "PENDENTE" and compra.url_checkout.startswith("https://checkout.stub.local/")
    assert (compra.creditos, Decimal(str(compra.preco_total_brl)), compra.expira_em_previsto) == (660, Decimal("844.80"), datetime(2026, 11, 1, 3, 0))
    assert pagamento._preferencias[compra.preferencia_id_externo]["referencia_externa"] == f"enriquecimento:{compra.id}"
    assert pagamento._preferencias[compra.preferencia_id_externo]["valor"] == 844.8
    assert ledger.saldo(db_session, A) == 30  # o navegador voltando do checkout não credita nada
    _, confirmada = pagar(db_session, pagamento, compra)
    assert confirmada.status == "APROVADA" and confirmada.expira_em == datetime(2026, 11, 1, 3, 0) and confirmada.movimento_id is not None
    comp = ledger.composicao(db_session, A, AGORA)
    assert (comp["franquia_restante"], comp["adicional_restante"], comp["saldo"]) == (30, 660, 690)  # separados
    cfg_depois, _ = config.config_vigente(db_session, A)
    assert (cfg_depois.franquia_creditos, cfg_depois.limite_creditos_pesquisa, cfg_depois.decisores_por_empresa_max) == (30, 30, 5)  # limites iguais
    # o saldo extra NÃO libera uma pesquisa maior que o limite por pesquisa do plano (30)
    maior = previa(db_session, eu(db_session), contas(db_session, 7), prov, d=5)
    assert maior.estimativa["viavel"] is False and maior.estimativa["bloqueios"][0]["codigo"] == "limite_por_pesquisa"
    movimento = db_session.get(EnriquecimentoMovimento, confirmada.movimento_id)
    assert (movimento.tipo, movimento.origem, movimento.delta_saldo) == ("COMPRA", "compra", 660)
    invariantes(db_session)


def test_webhook_repetido_valor_divergente_e_pagamento_pendente_nao_creditam_errado(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    pagamento, prov = StubPaymentProvider(), ProvedorPago()
    base = dict(aceite_expiracao=True, payment_provider=pagamento, email_pagador="a@b.com", provider=prov, fiscal=FISCAL, ator_id="1", agora=AGORA)

    c1 = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", **base)
    pagamento_id, _ = pagar(db_session, pagamento, c1)
    pacotes.confirmar_via_webhook(db_session, pagamento, pagamento_id, AGORA)  # o provedor reenvia o aviso
    pacotes.confirmar_via_webhook(db_session, pagamento, pagamento_id, AGORA)
    assert db_session.query(EnriquecimentoMovimento).filter_by(tenant_id=A, tipo="COMPRA").count() == 1 and ledger.saldo(db_session, A) == 400

    c2 = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", **base)
    _, divergente = pagar(db_session, pagamento, c2, valor=1.0)  # pagou R$ 1,00 por um pacote de R$ 540,00
    assert divergente.status == "REJEITADA" and ledger.saldo(db_session, A) == 400

    c3 = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", **base)
    id_pix, aguardando = pagar(db_session, pagamento, c3, status="pending")  # Pix/boleto ainda não compensou
    assert aguardando.status == "PENDENTE" and aguardando.confirmado_em is None and ledger.saldo(db_session, A) == 400
    pagamento._preferencias[c3.preferencia_id_externo]["status"] = "approved"  # compensou: o provedor avisa de novo
    assert pacotes.confirmar_via_webhook(db_session, pagamento, id_pix, AGORA).status == "APROVADA"
    assert ledger.saldo(db_session, A) == 800

    c4 = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", **base)
    _, recusada = pagar(db_session, pagamento, c4, status="rejected")
    assert recusada.status == "REJEITADA" and ledger.saldo(db_session, A) == 800


def test_pagamentos_de_outras_categorias_sao_ignorados_pelo_webhook_de_enriquecimento(client, db_session):
    pagamento = StubPaymentProvider()
    for referencia in ("123", "creditos:5", "enriquecimento:abc", ""):
        preferencia = pagamento.criar_preferencia(referencia, "x", 10.0, "a@b.com")
        pagamento_id = pagamento.aprovar(preferencia.id_externo)
        assert pacotes.confirmar_via_webhook(db_session, pagamento, pagamento_id, AGORA) is None


def test_credito_comprado_vence_no_fim_do_mes_junto_com_a_franquia_sem_acumular(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    pagamento, prov = StubPaymentProvider(), ProvedorPago()
    cfg, _ = config.config_vigente(db_session, A)
    ledger.preparar(db_session, A, cfg, AGORA)
    compra = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", aceite_expiracao=True, payment_provider=pagamento, email_pagador="a@b.com", provider=prov, fiscal=FISCAL,
                                    ator_id="1", agora=AGORA)
    pagar(db_session, pagamento, compra)
    ledger.travar_carteira(db_session, A)
    ledger.lancar(db_session, A, "CONSUMO", delta_saldo=-40, agora=AGORA)  # consome a franquia (30) e 10 do adicional
    db_session.commit()
    assert ledger.composicao(db_session, A, AGORA) == {"franquia_restante": 0, "adicional_restante": 390, "outros": 0, "saldo": 390}
    novembro = datetime(2026, 11, 2, 12, 0)
    ledger.preparar(db_session, A, cfg, novembro)
    db_session.commit()
    assert ledger.saldo(db_session, A) == 30  # só a franquia nova; os 390 restantes do pacote venceram
    expiracoes = db_session.query(EnriquecimentoMovimento).filter_by(tenant_id=A, tipo="EXPIRACAO").all()
    assert sorted((e.origem, e.delta_saldo) for e in expiracoes) == [("compra", -390)]
    assert ledger.composicao(db_session, A, novembro)["adicional_restante"] == 0


def test_compra_confirmada_na_virada_do_mes_vale_ate_o_fim_do_mes_da_confirmacao(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    pagamento, prov = StubPaymentProvider(), ProvedorPago()
    ultimo_minuto = datetime(2026, 11, 1, 2, 58)
    compra = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", aceite_expiracao=True, payment_provider=pagamento, email_pagador="a@b.com", provider=prov, fiscal=FISCAL,
                                    ator_id="1", agora=ultimo_minuto)
    _, confirmada = pagar(db_session, pagamento, compra, agora=datetime(2026, 11, 1, 3, 30))
    assert confirmada.expira_em_previsto == datetime(2026, 11, 1, 3, 0) and confirmada.expira_em == datetime(2026, 12, 1, 3, 0)
    assert ledger.composicao(db_session, A, datetime(2026, 11, 1, 3, 30))["adicional_restante"] == 400


def test_rentabilidade_usa_o_custo_contratual_e_ignora_a_compra_pontual_de_400_creditos(client, db_session):
    catalogo(db_session)
    from tests.integration.test_pesquisa_decisores_governanca import custo_contratual, lote

    lote(db_session)  # a compra pontual R$ 269,94 / 400 existe como linha, mas NÃO pode participar de custo, preço, margem nem configuração
    sem_contrato = pacotes.rentabilidade(db_session, "lusha")
    assert sem_contrato["origem_custo"] is None and all("margem_bruta_percentual" not in p for p in sem_contrato["pacotes"])
    custo_contratual(db_session, validar=False)  # aprovado; a validação do contrato não muda a conta
    r = pacotes.rentabilidade(db_session, "lusha")
    assert r["origem_custo"] == "contrato_v1" and r["custo_unitario_provedor_brl"] == "0.529411765" and Decimal(r["cambio_planejamento_brl"]) == Decimal("6")
    ativos = {p["codigo"]: p for p in r["pacotes"] if p["status"] == "ATIVO"}
    assert {c: p["markup_percentual"] for c, p in ativos.items()} == {"ENRIQ_400": "155.0", "ENRIQ_660": "141.8", "ENRIQ_1200": "128.6", "ENRIQ_3000": "104.0"}
    assert {c: p["margem_bruta_percentual"] for c, p in ativos.items()} == {"ENRIQ_400": "60.8", "ENRIQ_660": "58.6", "ENRIQ_1200": "56.2", "ENRIQ_3000": "51.0"}
    assert (ativos["ENRIQ_400"]["custo_total_brl"], ativos["ENRIQ_400"]["lucro_bruto_brl"]) == ("211.76", "328.24")  # 400 × R$ 0,529411765
    assert [p for p in r["pacotes"] if p["status"] == "CONTACT_SALES"][0].keys() == {"codigo", "creditos", "status"}
    # um câmbio de planejamento diferente (nova versão aprovada) recalcula sem tocar nos pacotes
    nova = custo.definir_custo(db_session, provedor="lusha", custo_mensal_usd="600", creditos_anuais=81600, cambio_planejamento_brl="5.00", ator_id="1",
                               tenant_auditoria=A, motivo="câmbio de planejamento 5,00", aprovar=True)
    assert nova.versao == 2
    depois = pacotes.rentabilidade(db_session, "lusha")
    assert depois["origem_custo"] == "contrato_v2" and depois["custo_unitario_provedor_brl"] == "0.441176471"
    assert next(p for p in depois["pacotes"] if p["codigo"] == "ENRIQ_400")["margem_bruta_percentual"] == "67.3"


# ============================================================ POC ====================================================================


def config_poc(db):
    cenario(db)
    aplicar_linha(db, "POC")


def test_poc_sem_autorizacao_aprovada_fica_bloqueada_sem_franquia_inventada(client, db_session):
    config_poc(db_session)
    cfg, motivo = config.config_vigente(db_session, A)
    assert cfg is None and motivo == "poc_sem_autorizacao"
    esperar_bloqueio("poc_sem_autorizacao", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=1))
    assert ledger.saldo(db_session, A) == 0


def test_poc_calcula_o_teto_pelas_tarifas_confirmadas_e_exige_politica_aprovada(client, db_session):
    with pytest.raises(ValidacaoFalhou, match="Não há teto calculável"):
        poc.calcular_teto(db_session, "lusha", 20)
    cenario(db_session)  # tarifas de teste: busca 0, e-mail 1, página 10, fator 1
    teto = poc.calcular_teto(db_session, "lusha", 20, 1)
    assert (teto["creditos_provedor_por_empresa"], teto["creditos_provedor_teto"], teto["creditos_cliente_teto"]) == (1, 20, 20)
    assert teto["custo_maximo_brl"] == "13.50" and teto["valor_venda_maximo_brl"] == "26.99"  # 20 × 0,67485 e 20 × 1,3497 = 26,994
    assert poc.calcular_teto(db_session, "lusha", 20, 3)["creditos_cliente_teto"] == 60


def test_poc_autorizacao_gera_config_do_tenant_pendente_e_so_depois_de_aprovada_libera_1_decisor(client, db_session):
    config_poc(db_session)
    resultado = poc.autorizar(db_session, A, provedor="lusha", empresas=20, decisores_por_empresa=1, ator_id="1", tenant_auditoria=A, motivo="POC cliente X")
    assert resultado["pendente_aprovacao"] is True and resultado["teto"]["creditos_cliente_teto"] == 20
    esperar_bloqueio("poc_sem_autorizacao", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=1))
    config.aprovar_config(db_session, resultado["config_id"], "1", A)
    cfg, motivo = config.config_vigente(db_session, A)
    assert motivo is None and cfg.origem == "tenant" and (cfg.franquia_creditos, cfg.periodicidade, cfg.decisores_por_empresa_max) == (20, "unica", 1)
    solic, prov = eu(db_session), ProvedorPago()
    with pytest.raises(ValidacaoFalhou, match="excede o máximo"):
        previa(db_session, solic, contas(db_session, 1), prov, d=2)
    p = previa(db_session, solic, contas(db_session, 20), prov, d=1)
    assert p.estimativa["viavel"] is True and p.estimativa["creditos_maximos"] == 20


def test_poc_so_pode_ser_autorizada_para_tenant_de_plano_poc_e_respeita_o_limite_de_1_decisor(client, db_session):
    cenario(db_session)  # plano comum, sem modo POC
    with pytest.raises(ValidacaoFalhou, match="não é uma POC"):
        poc.autorizar(db_session, A, provedor="lusha", empresas=5, ator_id="1", tenant_auditoria=A, motivo="x")
    aplicar_linha(db_session, "POC")
    with pytest.raises(ValidacaoFalhou, match="até 1 decisor"):
        poc.autorizar(db_session, A, provedor="lusha", empresas=5, decisores_por_empresa=2, ator_id="1", tenant_auditoria=A, motivo="x")


# ============================================================ Enterprise: limites por período ========================================


def config_enterprise(db, **limites):
    cenario(db)
    config.definir_config(db, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="contrato Enterprise", aprovar=True, campos=dict(
        franquia_creditos=1000, periodicidade="mensal", decisores_por_empresa_max=5, limite_creditos_pesquisa=1000, **limites))


def test_enterprise_limita_pesquisas_empresas_e_contatos_por_periodo(client, db_session):
    config_enterprise(db_session, limite_pesquisas_periodo=2, limite_empresas_periodo=5, limite_contatos_periodo=8)
    solic, prov = eu(db_session), ProvedorPago()
    p1 = confirmar(db_session, solic, previa(db_session, solic, contas(db_session, 2), prov, d=2), prov, "chave-enterprise-1", AGORA)
    assert p1.estado == "reservada"
    uso = previa(db_session, solic, contas(db_session, 1), prov, d=1, agora=AGORA).estimativa["uso_no_periodo"]
    assert uso == {"pesquisas": 1, "empresas": 2, "contatos": 4}
    excede_contatos = previa(db_session, solic, contas(db_session, 3), prov, d=2, agora=AGORA)  # 4 + 6 > 8
    assert excede_contatos.estimativa["bloqueios"][0]["codigo"] == "limite_contatos_periodo"
    excede_empresas = previa(db_session, solic, contas(db_session, 4), prov, d=1, agora=AGORA)  # 2 + 4 > 5
    assert "limite_empresas_periodo" in {b["codigo"] for b in excede_empresas.estimativa["bloqueios"]}
    cabe = previa(db_session, solic, contas(db_session, 3), prov, d=1, agora=AGORA)  # 2 + 3 = 5 empresas, 4 + 3 = 7 contatos
    assert cabe.estimativa["viavel"] is True
    p2 = confirmar(db_session, solic, cabe, prov, "chave-enterprise-2", AGORA)
    assert p2.estado == "reservada"
    terceira = previa(db_session, solic, contas(db_session, 1), prov, d=1, agora=AGORA)
    assert "limite_pesquisas_periodo" in {b["codigo"] for b in terceira.estimativa["bloqueios"]}
    # no mês seguinte os contadores recomeçam
    proximo = previa(db_session, solic, contas(db_session, 1), prov, d=1, agora=datetime(2026, 11, 3, 12, 0))
    assert "limite_pesquisas_periodo" not in {b["codigo"] for b in proximo.estimativa["bloqueios"]}


def test_pesquisa_que_falhou_sem_consumo_nao_conta_no_limite_do_periodo(client, db_session, fake_graph):
    config_enterprise(db_session, limite_pesquisas_periodo=1)
    solic, prov = eu(db_session), ProvedorPago(roteiro=[erro_seguro()])
    falhou = rodar(db_session, fake_graph, solic, contas(db_session, 1), prov, d=1)
    assert falhou.estado == "falha" and falhou.creditos_consumidos == 0
    agora = config.agora_utc()
    depois = previa(db_session, solic, contas(db_session, 1), prov, d=1, agora=agora)
    assert depois.estimativa["uso_no_periodo"]["pesquisas"] == 0 and depois.estimativa["viavel"] is True


def test_limites_do_enterprise_sao_validados_versionados_e_auditados(client, db_session):
    cenario(db_session)
    with pytest.raises(ValidacaoFalhou):
        config.definir_config(db_session, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="x", campos=dict(limite_empresas_periodo=-1))
    with pytest.raises(ValidacaoFalhou):
        config.definir_config(db_session, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="x", campos=dict(limite_contatos_periodo=1.5))
    v1 = config.definir_config(db_session, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="v1", aprovar=True, campos=dict(
        franquia_creditos=100, periodicidade="mensal", decisores_por_empresa_max=5, limite_creditos_pesquisa=100, limite_empresas_periodo=10))
    v2 = config.definir_config(db_session, plano_id=None, tenant_id=A, ator_id="1", tenant_auditoria=A, motivo="v2", aprovar=True, campos=dict(
        franquia_creditos=100, periodicidade="mensal", decisores_por_empresa_max=5, limite_creditos_pesquisa=100, limite_empresas_periodo=20))
    assert (v1.versao, v2.versao) == (1, 2) and config.config_vigente(db_session, A)[0].limite_empresas_periodo == 20


# ============================================================ ICP, site e QSA ========================================================


def test_icp_com_milhares_de_empresas_nao_tem_limite_e_so_a_selecao_explicita_consome_credito(client, db_session):
    liberar_lusha(db_session, "Starter")
    db_session.add_all([Conta(tenant_id=A, nome=f"Empresa ICP {i}", dominio=f"icp{i}.com.br", cnpj=f"{i:014d}", status="prospectada", icp_id=None)
                        for i in range(1, 2001)])
    db_session.commit()
    assert db_session.query(Conta).filter_by(tenant_id=A).count() == 2000  # a franquia (30) não limita o tamanho do ICP
    solic, prov = eu(db_session), ProvedorPago()
    escolhidas = db_session.query(Conta).filter_by(tenant_id=A).order_by(Conta.id).limit(3).all()
    p = confirmar(db_session, solic, previa(db_session, solic, escolhidas, prov, d=2), prov)
    assert p.total_empresas == 3 and ledger.reservado(db_session, A) == 6  # só as 3 escolhidas, nunca as 2.000
    assert db_session.query(PesquisaDecisores).count() == 1


def test_a_rota_de_previa_recusa_o_icp_inteiro_mesmo_com_franquia(client, db_session, prov_api):
    liberar_lusha(db_session, "Starter")
    for corpo in ({"icp_id": 1}, {"todas": True}, {"conta_ids": [], "icp_id": 1}):
        assert client.post(f"{URL}/previa", json=corpo).status_code == 422
    assert prov_api.chamadas == []


def test_analise_de_site_fica_fora_da_franquia_lusha_e_usa_a_franquia_de_ia(client, db_session, fake_llm, fake_web_search):
    from app.services import conta_service

    liberar_lusha(db_session, "Starter")
    ledger.preparar(db_session, A, config.config_vigente(db_session, A)[0], AGORA)
    db_session.commit()
    conta = contas(db_session, 1)[0]
    antes = (ledger.saldo(db_session, A), db_session.query(EnriquecimentoMovimento).count())
    conta_service.enriquecer(db_session, A, "1", conta.id, fake_llm, lambda dominio: "=== https://x.com.br ===\nConteúdo institucional.", fake_web_search,
                             StubPlanLimitsProvider())
    assert (ledger.saldo(db_session, A), db_session.query(EnriquecimentoMovimento).count()) == antes  # nada de Lusha: razão intacto
    assert db_session.query(ExecucaoIa).filter_by(tenant_id=A, workload_codigo="website_analysis").count() >= 1  # contabilizada na categoria de IA


def test_analise_de_site_respeita_o_proprio_limite_semanal_do_plano(client, db_session, fake_llm, fake_web_search):
    from app.services import conta_service
    from app.services.errors import RegraNegocioViolada

    liberar_lusha(db_session, "Starter")  # a franquia Lusha cheia não muda nada para o site
    limites = StubPlanLimitsProvider(limite_enriquecimento_site_semanal={A: 1})
    c1, c2 = contas(db_session, 2)
    site = lambda dominio: "=== https://x.com.br ===\nConteúdo."  # noqa: E731
    conta_service.enriquecer(db_session, A, "1", c1.id, fake_llm, site, fake_web_search, limites)
    with pytest.raises(RegraNegocioViolada):
        conta_service.enriquecer(db_session, A, "1", c2.id, fake_llm, site, fake_web_search, limites)


# ============================================================ API, permissões e isolamento ===========================================


def test_painel_do_tenant_mostra_composicao_validade_limites_e_disponibilidade_de_compra(client, db_session, prov_api):
    liberar_lusha(db_session, "Starter")
    d = client.get(f"{URL}/painel").json()
    assert d["plano"]["modo"] == "franquia_fixa" and d["plano"]["limite_creditos_pesquisa"] == 30 and d["plano"]["decisores_por_empresa_max"] == 5
    assert d["composicao"]["franquia_restante"] == 30 and d["composicao"]["adicional_restante"] == 0 and d["composicao"]["acumula"] is False
    assert d["composicao"]["expira_em"] and d["compra_adicional"] == {"disponivel": True, "motivos": []}
    assert d["uso_no_periodo"] == {"pesquisas": 0, "empresas": 0, "contatos": 0}


def test_rotas_de_pacotes_e_compras_para_o_tenant(client, db_session, prov_api):
    liberar_lusha(db_session, "Starter")
    catalogo(db_session)
    pagamento = StubPaymentProvider()
    app.dependency_overrides[get_payment_provider] = lambda: pagamento
    app.dependency_overrides[get_fiscal_provider] = lambda: FISCAL
    vitrine = client.get(f"{URL}/pacotes").json()
    assert vitrine["compra_disponivel"] is True and len(vitrine["pacotes"]) == 5 and vitrine["expira_em_previsto"]
    sem_aceite = client.post(f"{URL}/compras", json={"pacote": "ENRIQ_400", "aceite_expiracao": False})
    assert sem_aceite.status_code in (400, 422) and pagamento._preferencias == {}
    assert client.post(f"{URL}/compras", json={"pacote": "ENRIQ_400", "aceite_expiracao": True, "preco": 1}).status_code == 422  # preço nunca vem do cliente
    ok = client.post(f"{URL}/compras", json={"pacote": "ENRIQ_400", "aceite_expiracao": True})
    assert ok.status_code == 201
    corpo = ok.json()
    assert corpo["preco_total_brl"] == "540.00" and corpo["status"] == "PENDENTE" and corpo["url_checkout"] and corpo["expira_em_previsto"]
    assert [c["id"] for c in client.get(f"{URL}/compras").json()] == [corpo["id"]]
    assert client.post(f"{URL}/compras", json={"pacote": "ENRIQ_ACIMA_3000", "aceite_expiracao": True}).status_code in (400, 422)
    assert client.post(f"{URL}/compras", json={"pacote": "NAO_EXISTE", "aceite_expiracao": True}).status_code == 404


def test_vendedor_nao_compra_nem_ve_compras_e_compra_bloqueada_sem_lusha_explica_o_motivo(client, db_session, prov_api):
    catalogo(db_session)
    bloqueada = client.post(f"{URL}/compras", json={"pacote": "ENRIQ_400", "aceite_expiracao": True})
    assert bloqueada.status_code == 409 and bloqueada.json()["codigo"] and bloqueada.json()["bloqueios"]
    assert client.get(f"{URL}/pacotes").json()["compra_disponivel"] is False
    with pytest.raises(NaoAutorizado):
        from app.api.v1.pesquisas_decisores import minhas_compras
        from app.models.usuario import Usuario

        minhas_compras(Usuario(id=99, tenant_id=A, papel="user", nome="v", email="v@x.com"), db_session)


def test_webhook_assinado_do_mercado_pago_credita_a_compra_e_assinatura_invalida_nao(client, db_session, prov_api, monkeypatch):
    liberar_lusha(db_session, "Starter")
    catalogo(db_session)
    pagamento = StubPaymentProvider()
    app.dependency_overrides[get_payment_provider] = lambda: pagamento
    app.dependency_overrides[get_fiscal_provider] = lambda: FISCAL
    compra = client.post(f"{URL}/compras", json={"pacote": "ENRIQ_400", "aceite_expiracao": True}).json()
    pagamento_id = pagamento.aprovar(db_session.get(EnriquecimentoCompra, compra["id"]).preferencia_id_externo)
    segredo = "segredo-webhook-mp-teste"
    monkeypatch.setattr(settings, "mercadopago_webhook_secret", segredo)

    def assinar(request_id="req-1"):
        ts = "1760000000"
        v1 = hmac.new(segredo.encode(), f"id:{pagamento_id.lower()};request-id:{request_id};ts:{ts};".encode(), hashlib.sha256).hexdigest()
        return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}

    assert client.post(f"/api/v1/webhooks/mercadopago?data.id={pagamento_id}", headers={"x-signature": "ts=1,v1=errada", "x-request-id": "r"}).status_code in (401, 403)
    assert ledger.saldo(db_session, A) == 0
    assert client.post(f"/api/v1/webhooks/mercadopago?data.id={pagamento_id}", headers=assinar()).status_code == 200
    assert client.post(f"/api/v1/webhooks/mercadopago?data.id={pagamento_id}", headers=assinar()).status_code == 200  # reenvio
    db_session.expire_all()
    assert db_session.get(EnriquecimentoCompra, compra["id"]).status == "APROVADA"
    assert ledger.composicao(db_session, A)["adicional_restante"] == 400 and db_session.query(EnriquecimentoMovimento).filter_by(tipo="COMPRA").count() == 1


def test_compras_e_saldo_de_um_tenant_nao_aparecem_para_outro(client, db_session, prov_api):
    liberar_lusha(db_session, "Starter")
    catalogo(db_session)
    preparar_tenant_b(db_session)  # B tem licença no mesmo plano (mesma franquia), mas carteira e compras próprias
    dados_fiscais(db_session, B, "99888777000166")
    pagamento = StubPaymentProvider()
    base = dict(aceite_expiracao=True, payment_provider=pagamento, email_pagador="x@x.com", provider=prov_api, fiscal=FISCAL, agora=AGORA)
    compra_a = pacotes.iniciar_compra(db_session, A, "ENRIQ_400", ator_id="1", **base)
    pagar(db_session, pagamento, compra_a)
    assert pacotes.listar_compras(db_session, B) == [] and ledger.saldo(db_session, B) == 0
    compra_b = pacotes.iniciar_compra(db_session, B, "ENRIQ_660", ator_id="9", **base)
    pagar(db_session, pagamento, compra_b)
    assert [c.id for c in pacotes.listar_compras(db_session, A)] == [compra_a.id] and [c.id for c in pacotes.listar_compras(db_session, B)] == [compra_b.id]
    assert (ledger.composicao(db_session, A, AGORA)["adicional_restante"], ledger.composicao(db_session, B, AGORA)["adicional_restante"]) == (400, 660)
    invariantes(db_session, A)
    invariantes(db_session, B)


def test_rota_publica_de_franquias_e_pacotes_nao_exige_login_e_nao_expoe_custo_nem_margem(client, db_session):
    catalogo(db_session)
    resposta = client.get("/api/v1/planos/enriquecimento")
    assert resposta.status_code == 200
    d = resposta.json()
    nomes = {p["plano"]: p for p in d["planos"]}
    assert list(nomes) == ["POC", "Teste gratuito", "Starter", "Professional", "Business", "Corporate", "Enterprise"]
    assert (nomes["Teste gratuito"]["franquia_creditos"], nomes["Teste gratuito"]["decisores_por_empresa_max"]) == (30, 3)
    assert (nomes["Corporate"]["franquia_creditos"], nomes["Corporate"]["limite_creditos_pesquisa"], nomes["Corporate"]["decisores_por_empresa_max"]) == (180, 180, 30)
    assert nomes["POC"]["modo"] == "poc_autorizada" and "franquia_creditos" not in nomes["POC"] and nomes["Enterprise"]["modo"] == "sob_consulta"
    assert [p["preco_total_brl"] for p in d["pacotes"]] == ["540.00", "844.80", "1452.00", "3240.00", None]
    texto = resposta.text.lower()
    assert all(palavra not in texto for palavra in ("margem", "markup", "custo", "mensalidade", "lote"))
    assert "preco_mensal" not in texto and d["observacoes"]


def test_rotas_administrativas_exigem_super_admin_e_registram_auditoria(client, db_session, prov_api):
    liberar_lusha(db_session, "Starter")
    # o usuário de teste é super_admin: as rotas respondem; um admin comum não passa
    assert client.get(f"{ADMIN}/matriz").status_code == 200
    aplicar = client.post(f"{ADMIN}/matriz/aplicar", json={"mapeamento": {"Professional": plano_id(db_session)}})
    assert aplicar.status_code == 200 and aplicar.json()["aplicados"][0]["plano"] == "Plano Padrão Teste"
    pacote = client.put(f"{ADMIN}/pacotes", json={"codigo": "ENRIQ_400", "nome": "400 créditos", "quantidade_creditos": 400, "preco_unitario_brl": "1.35",
                                                  "preco_total_brl": "540.00", "motivo": "catálogo inicial"})
    assert pacote.status_code == 200 and pacote.json()["pendente_aprovacao"] is True
    assert client.put(f"{ADMIN}/pacotes", json={"codigo": "ENRIQ_BAD", "nome": "Ruim", "quantidade_creditos": 10, "preco_unitario_brl": "1.00",
                                                "preco_total_brl": "9.00", "motivo": "total errado"}).status_code in (400, 422)
    assert client.get(f"{URL}/pacotes").json()["pacotes"] == []  # pendente não aparece no catálogo
    assert client.post(f"{ADMIN}/pacotes/{pacote.json()['id']}/aprovar").status_code == 200
    assert [p["codigo"] for p in client.get(f"{URL}/pacotes").json()["pacotes"]] == ["ENRIQ_400"]
    rent = client.get(f"{ADMIN}/pacotes/rentabilidade").json()
    assert rent["pacotes"][0]["margem_bruta_percentual"] == "60.8" and rent["origem_custo"] == "contrato_v1"
    teto = client.post(f"{ADMIN}/poc/teto", json={"empresas": 10}).json()
    assert teto["creditos_cliente_teto"] == 10
    eventos = {a["evento"] for a in client.get(f"{ADMIN}/auditoria").json()}
    assert {"enriquecimento_config_definida", "enriquecimento_config_aprovada", "enriquecimento_pacote_definido", "enriquecimento_pacote_aprovado"} <= eventos
    assert client.get(f"{ADMIN}/compras").status_code == 200


def test_admin_comum_nao_acessa_a_administracao_de_matriz_pacotes_poc_e_auditoria(client, db_session, monkeypatch):
    from app.api.deps import get_usuario_atual
    from app.models.usuario import Usuario

    comum = Usuario(id=77, tenant_id=A, papel="admin", nome="Admin", email="admin@x.com", ativo=True)
    app.dependency_overrides[get_usuario_atual] = lambda: comum
    for metodo, caminho, corpo in (("get", "/matriz", None), ("post", "/matriz/aplicar", {}), ("get", "/pacotes", None),
                                   ("put", "/pacotes", {"codigo": "ENRIQ_X", "nome": "X", "quantidade_creditos": 10, "preco_unitario_brl": "1.00", "motivo": "xxx"}),
                                   ("post", "/pacotes/1/aprovar", None), ("get", "/pacotes/rentabilidade", None), ("post", "/poc/teto", {"empresas": 5}),
                                   ("post", "/poc/autorizar", {"empresas": 5, "tenant_id": A, "motivo": "xxx"}), ("get", "/auditoria", None),
                                   ("get", "/compras", None)):
        resposta = getattr(client, metodo)(f"{ADMIN}{caminho}", **({"json": corpo} if corpo is not None else {}))
        assert resposta.status_code in (401, 403), (metodo, caminho, resposta.status_code)
