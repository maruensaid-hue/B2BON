"""Custo contratual do provedor, validação do contrato, custo efetivo, orçamento global dentro da capacidade, venda de pacotes com nota fiscal e conciliação,
contestação sem estorno automático e estorno manual de créditos.

Base econômica (informada pelo PO): USD 600/mês, 81.600 créditos/ano (6.800/mês), câmbio de planejamento R$ 6,00 ⇒ R$ 0,529411765 por crédito e R$ 3.600,00/mês.
A compra pontual de 400 créditos por R$ 269,94 foi desconsiderada e não participa de nada. Provedor, pagamento e emissor fiscal sempre simulados."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.api.deps import get_contact_enrichment_provider, get_fiscal_provider, get_payment_provider, get_usuario_atual
from app.contexts.enriquecimento import config, custo, estornos, ledger, pacotes, painel, precos, vendas
from app.core.config import settings
from app.main import app
from app.models.auditoria import AuditLog
from app.models.enriquecimento_creditos import EnriquecimentoCompra, EnriquecimentoEstornoCompra, EnriquecimentoMovimento, EnriquecimentoNotaFiscal
from app.models.usuario import Usuario
from app.providers.fiscal.desativado import FiscalDesativado
from app.providers.fiscal.stub import StubFiscalProvider
from app.providers.payment.stub import StubPaymentProvider
from app.services.errors import NaoAutorizado, PesquisaBloqueada, ValidacaoFalhou
from tests.integration.test_enriquecimento_matriz_pacotes import catalogo, dados_fiscais, liberar_lusha
from tests.integration.test_pesquisa_decisores_governanca import (
    A,
    ADMIN,
    URL,
    ProvedorPago,
    cenario,
    contas,
    custo_contratual,
    esperar_bloqueio,
    eu,
    invariantes,
    previa,
)

AGORA = datetime(2026, 10, 15, 15, 0)
CHECKLIST = {i: True for i in custo.CHECKLIST_CONTRATO}


@pytest.fixture()
def prov_api(client):
    provedor = ProvedorPago()
    app.dependency_overrides[get_contact_enrichment_provider] = lambda: provedor
    return provedor


def comprar(db, pagamento, prov, fiscal, pacote="ENRIQ_400", taxas=None, liquido=None, pagar=True):
    compra = pacotes.iniciar_compra(db, A, pacote, aceite_expiracao=True, payment_provider=pagamento, email_pagador="a@b.com", provider=prov, fiscal=fiscal,
                                    ator_id="1", agora=AGORA)
    if not pagar:
        return compra, None
    pagamento_id = pagamento.aprovar(compra.preferencia_id_externo, taxas=taxas, valor_liquido=liquido)
    return pacotes.confirmar_via_webhook(db, pagamento, pagamento_id, AGORA, fiscal=fiscal), pagamento_id


# ============================================================ custo contratual =====================================================


def test_custo_contratual_deriva_custo_unitario_e_mensal_e_so_vale_aprovado(client, db_session):
    nova = custo.definir_custo(db_session, provedor="lusha", custo_mensal_usd="600", creditos_anuais=81600, cambio_planejamento_brl="6.00", ator_id="1",
                               tenant_auditoria=A, motivo="base econômica do PO")
    assert custo.custo_vigente(db_session, "lusha") is None  # pendente não vale
    custo.aprovar_custo(db_session, nova.id, "1", A)
    vigente = custo.custo_vigente(db_session, "lusha")
    assert (vigente.creditos_mensais, vigente.contrato_validado) == (6800, False)
    assert precos.exibir(vigente.custo_unitario_usd, 9) == Decimal("0.088235294") and precos.exibir(vigente.custo_unitario_brl, 9) == Decimal("0.529411765")
    assert vigente.custo_mensal_brl == Decimal("3600.00") and vigente.cambio_planejamento_brl == Decimal(6)
    assert custo.capacidade_mensal(db_session, "lusha") == 6800


@pytest.mark.parametrize("campos,trecho", [
    (dict(creditos_anuais=81601), "divisível por 12"), (dict(custo_mensal_usd="-1"), "positivo"), (dict(custo_mensal_usd="abc"), "decimal"),
    (dict(cambio_planejamento_brl="0"), "positivo"), (dict(creditos_anuais=0), "inteiro positivo"), (dict(creditos_anuais=True), "inteiro positivo"),
    (dict(motivo=" "), "motivo"),
])
def test_custo_contratual_recusa_valores_invalidos(client, db_session, campos, trecho):
    base = dict(provedor="lusha", custo_mensal_usd="600", creditos_anuais=81600, cambio_planejamento_brl="6.00", ator_id="1", tenant_auditoria=A, motivo="x")
    with pytest.raises(ValidacaoFalhou, match=trecho):
        custo.definir_custo(db_session, **{**base, **campos})


def test_sem_custo_contratual_a_lusha_fica_bloqueada_antes_de_reservar(client, db_session):
    cenario(db_session, contrato=False)
    prov = ProvedorPago()
    esperar_bloqueio("custo_provedor_nao_configurado", lambda: previa(db_session, eu(db_session), contas(db_session, 1), prov))
    assert prov.chamadas == [] and ledger.reservado(db_session, A) == 0
    assert "custo_provedor_nao_configurado" in {m["codigo"] for m in config.motivos_de_indisponibilidade(db_session, A, prov)}


def test_custo_aprovado_mas_contrato_nao_validado_continua_bloqueando(client, db_session):
    cenario(db_session, contrato=False)
    custo_contratual(db_session, validar=False)
    prov = ProvedorPago()
    esperar_bloqueio("contrato_provedor_nao_validado", lambda: previa(db_session, eu(db_session), contas(db_session, 1), prov))
    assert prov.chamadas == []


def test_validar_contrato_exige_checklist_completo_evidencia_e_o_fato_do_saldo(client, db_session):
    cenario(db_session, contrato=False)
    linha = custo_contratual(db_session, validar=False)
    base = dict(saldo_transferivel=False, evidencia="Contrato assinado em 2026-10-01, cláusulas 3 e 4", ator_id="1", tenant_auditoria=A)
    with pytest.raises(ValidacaoFalhou, match="Contrato não validado"):
        custo.validar_contrato(db_session, linha.id, checklist={**CHECKLIST, "deduplicacao_confirmada": False}, **base)
    with pytest.raises(ValidacaoFalhou, match="Contrato não validado"):
        custo.validar_contrato(db_session, linha.id, checklist={}, **base)
    with pytest.raises(ValidacaoFalhou, match="transferir saldo"):
        custo.validar_contrato(db_session, linha.id, checklist=CHECKLIST, **{**base, "saldo_transferivel": None})
    with pytest.raises(ValidacaoFalhou, match="evidência"):
        custo.validar_contrato(db_session, linha.id, checklist=CHECKLIST, **{**base, "evidencia": "ok"})
    assert not custo.custo_vigente(db_session, "lusha").contrato_validado
    custo.validar_contrato(db_session, linha.id, checklist=CHECKLIST, **base)
    vigente = custo.custo_vigente(db_session, "lusha")
    assert vigente.contrato_validado and vigente.saldo_transferivel is False
    p = previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=1)
    assert p.estimativa["viavel"] is True  # com política e orçamento aprovados, a pesquisa é liberada


def test_nova_versao_do_custo_precisa_ser_validada_de_novo(client, db_session):
    cenario(db_session)
    custo.definir_custo(db_session, provedor="lusha", custo_mensal_usd="650", creditos_anuais=81600, cambio_planejamento_brl="6.00", ator_id="1",
                        tenant_auditoria=A, motivo="reajuste do fornecedor", aprovar=True)
    assert custo.custo_vigente(db_session, "lusha").versao == 2
    esperar_bloqueio("contrato_provedor_nao_validado", lambda: previa(db_session, eu(db_session), contas(db_session, 1), ProvedorPago(), d=1))


def test_orcamento_global_nunca_passa_da_capacidade_do_contrato(client, db_session):
    cenario(db_session)
    kw = dict(provedor="lusha", alerta_percentual=80, ator_id="1", tenant_auditoria=A, motivo="teto de USD 600")
    with pytest.raises(ValidacaoFalhou, match="capacidade do contrato"):
        config.definir_orcamento_global(db_session, limite_creditos=6801, **kw)
    config.definir_orcamento_global(db_session, limite_creditos=6800, aprovar=True, **kw)
    assert config.orcamento_vigente(db_session, "lusha").limite_creditos == 6800
    menor = custo.definir_custo(db_session, provedor="lusha", custo_mensal_usd="600", creditos_anuais=60000, cambio_planejamento_brl="6.00", ator_id="1",
                                tenant_auditoria=A, motivo="contrato menor")  # 5.000/mês
    with pytest.raises(ValidacaoFalhou, match="excede a capacidade"):
        custo.aprovar_custo(db_session, menor.id, "1", A)


def test_politica_com_o_metodo_contrato_mensal_usa_o_custo_de_planejamento(client, db_session):
    base = dict(provedor="lusha", creditos_busca_por_resultado=0, creditos_email=1, creditos_telefone=None, revelar_emails=True, revelar_telefones=False,
                tamanho_pagina_busca=10, creditos_cliente_por_credito_provedor=1, markup_percentual=Decimal("100"), metodo_custo="contrato_mensal",
                lote_compra_id=None, casas_exibicao=2, fonte_tarifas="manual", ator_id="1", tenant_auditoria=A, motivo="teste", tamanho_pagina_minimo=10,
                tamanho_pagina_maximo=100)
    with pytest.raises(ValidacaoFalhou, match="custo contratual"):
        config.definir_politica(db_session, **base)
    custo_contratual(db_session, validar=False)
    pol = config.definir_politica(db_session, **base)
    assert precos.exibir(pol.custo_unitario_brl, 9) == Decimal("0.529411765") and precos.exibir(pol.preco_unitario_brl, 9) == Decimal("1.058823529")


def test_custo_efetivo_por_credito_consumido_cresce_com_a_ociosidade_e_usa_o_pagamento_real(client, db_session):
    custo_contratual(db_session)
    ledger.travar_carteira(db_session, A)
    ledger.lancar(db_session, A, "CONSUMO", delta_saldo=-1700, provedor="lusha", provedor_delta_consumido=1700, agora=AGORA)
    db_session.commit()
    plano = custo.custo_efetivo(db_session, "lusha", "2026-10")
    assert (plano["creditos_consumidos"], plano["creditos_ociosos"], plano["ociosidade_percentual"]) == (1700, 5100, "75.0")
    assert plano["base_do_calculo"] == "planejamento" and plano["custo_mensal_planejamento_brl"] == "3600.00" and plano["aviso"]
    assert Decimal(plano["custo_efetivo_por_credito_consumido_brl"]) == precos.interna(Decimal(3600) / Decimal(1700))  # R$ 2,117647058824
    custo.registrar_pagamento(db_session, provedor="lusha", referencia="FAT-2026-10", periodo="2026-10", valor_usd="600", taxa_cambio_efetiva="5.80",
                              encargos_brl="25.50", pago_em=datetime(2026, 10, 5), observacao="fatura de outubro", ator_id="1", tenant_auditoria=A)
    custo.registrar_pagamento(db_session, provedor="lusha", referencia="FAT-2026-09", periodo="2026-09", valor_usd="600", taxa_cambio_efetiva="6.20",
                              pago_em=datetime(2026, 9, 5), observacao=None, ator_id="1", tenant_auditoria=A)
    real = custo.custo_efetivo(db_session, "lusha", "2026-10")
    assert real["base_do_calculo"] == "pagamentos_efetivos" and real["custo_mensal_efetivo_brl"] == "3505.50"  # 600 × 5,80 + 25,50 (o de setembro não entra)
    assert real["custo_mensal_planejamento_brl"] == "3600.00" and real["aviso"] is None and len(real["pagamentos"]) == 1
    assert Decimal(real["custo_efetivo_por_credito_consumido_brl"]) == precos.interna(Decimal("3505.50") / Decimal(1700))
    assert custo.custo_efetivo(db_session, "lusha", "2026-08")["custo_efetivo_por_credito_consumido_brl"] is None  # sem consumo, sem custo por crédito


def test_pagamento_ao_provedor_valida_periodo_referencia_unica_e_nao_inventa_encargos(client, db_session):
    base = dict(provedor="lusha", periodo="2026-10", valor_usd="600", taxa_cambio_efetiva="5.9", pago_em=datetime(2026, 10, 5), observacao=None, ator_id="1", tenant_auditoria=A)
    pagamento = custo.registrar_pagamento(db_session, referencia="FAT-1", **base)
    assert pagamento.encargos_brl == 0 and pagamento.valor_brl_total == Decimal("3540.00")  # sem encargos informados, nenhum encargo é presumido
    for campos, trecho in ((dict(referencia="FAT-1"), "Já existe"), (dict(referencia="FAT-2", periodo="2026-13"), "AAAA-MM"), (dict(referencia=" "), "referência"),
                           (dict(referencia="FAT-3", encargos_brl="-1"), "negativos"), (dict(referencia="FAT-4", valor_usd="0"), "positivo")):
        with pytest.raises(ValidacaoFalhou, match=trecho):
            custo.registrar_pagamento(db_session, **{**base, **campos})
    with pytest.raises(RuntimeError, match="append-only"):
        pagamento.valor_usd = 1
        db_session.commit()
    db_session.rollback()


def test_a_compra_pontual_de_400_creditos_nao_participa_de_custo_preco_margem_nem_configuracao(client, db_session):
    from tests.integration.test_pesquisa_decisores_governanca import lote

    lote(db_session)  # existe como linha legada, mas nada a consulta
    catalogo(db_session)
    custo_contratual(db_session, validar=False)
    r = pacotes.rentabilidade(db_session, "lusha")
    assert r["origem_custo"] == "contrato_v1" and r["custo_unitario_provedor_brl"] == "0.529411765"
    assert custo.custo_efetivo(db_session, "lusha", "2026-10")["custo_unitario_nominal_brl"].startswith("0.52941176")


# ============================================================ APIs de custo e dashboard administrativo ================================


def test_api_de_custo_contrato_pagamento_e_visao_administrativa(client, db_session, prov_api):
    cenario(db_session, contrato=False)
    r = client.put(f"{ADMIN}/custo", json={"custo_mensal_usd": "600", "creditos_anuais": 81600, "cambio_planejamento_brl": "6.00", "motivo": "base do PO"})
    assert r.status_code == 200 and r.json()["creditos_mensais"] == 6800 and r.json()["aprovada"] is False
    cid = r.json()["id"]
    assert client.post(f"{ADMIN}/custo/{cid}/validar-contrato", json={"checklist": CHECKLIST, "saldo_transferivel": False, "evidencia": "contrato 2026"}).status_code in (400, 422)
    assert client.post(f"{ADMIN}/custo/{cid}/aprovar").status_code == 200
    incompleto = client.post(f"{ADMIN}/custo/{cid}/validar-contrato", json={"checklist": {"ciclo_mensal_confirmado": True}, "saldo_transferivel": False,
                                                                           "evidencia": "contrato assinado em 2026-10-01"})
    assert incompleto.status_code in (400, 422)
    ok = client.post(f"{ADMIN}/custo/{cid}/validar-contrato", json={"checklist": CHECKLIST, "saldo_transferivel": False, "evidencia": "contrato assinado em 2026-10-01"})
    assert ok.status_code == 200 and ok.json()["contrato_validado"] is True
    pagamento = client.post(f"{ADMIN}/pagamentos-provedor", json={"referencia": "FAT-OUT", "periodo": config.periodo_de(config.agora_utc()), "valor_usd": "600",
                                                                  "taxa_cambio_efetiva": "5.87", "encargos_brl": "12.34", "pago_em": "2026-10-05T10:00:00"})
    assert pagamento.status_code == 201 and pagamento.json()["valor_brl_total"] == "3534.34"
    assert client.post(f"{ADMIN}/pagamentos-provedor", json={"referencia": "FAT-OUT", "periodo": "2026-10", "valor_usd": "1", "taxa_cambio_efetiva": "5",
                                                             "pago_em": "2026-10-05T10:00:00"}).status_code in (400, 422)
    lista = client.get(f"{ADMIN}/custo").json()
    assert lista["versoes"][0]["vigente"] is True and len(lista["checklist_contrato"]) == 6 and lista["efetivo_no_mes"]["base_do_calculo"] == "pagamentos_efetivos"
    visao = client.get(f"{ADMIN}/orcamento-global?provedor=lusha").json()
    assert visao["contrato_validado"] is True and visao["custo_contratual"]["custo_unitario_nominal_brl"].startswith("0.52941176")
    assert visao["orcamento_global_usd_equivalente"] == "88.24"  # orçamento do cenário de teste: 1.000 créditos × USD 0,088235294
    assert visao["conciliacao_vendas"]["vendas_aprovadas"] == 0


def test_rotas_novas_de_administracao_exigem_super_admin(client, db_session):
    comum = Usuario(id=77, tenant_id=A, papel="admin", nome="Admin", email="admin@x.com", ativo=True)
    app.dependency_overrides[get_usuario_atual] = lambda: comum
    for metodo, caminho, corpo in (("get", "/custo", None), ("put", "/custo", {"custo_mensal_usd": "600", "creditos_anuais": 81600, "cambio_planejamento_brl": "6", "motivo": "xxx"}),
                                   ("post", "/custo/1/aprovar", None), ("post", "/custo/1/validar-contrato", {"checklist": CHECKLIST, "saldo_transferivel": False, "evidencia": "xxxxxxxxxxxx"}),
                                   ("get", "/custo/efetivo", None), ("post", "/pagamentos-provedor", {"referencia": "FAT", "periodo": "2026-10", "valor_usd": "1",
                                                                                                    "taxa_cambio_efetiva": "1", "pago_em": "2026-10-05T10:00:00"}),
                                   ("get", "/vendas", None), ("post", "/compras/1/emitir-nota", None), ("get", "/estornos", None),
                                   ("post", "/compras/1/estornos", {"tipo": "ESTORNO", "creditos": 1, "justificativa": "xxxxxxxxxxxx", "evidencia": "xxxxxx"}),
                                   ("post", "/estornos/1/decidir", {"aprovar": True, "motivo": "xxxxxx"})):
        resposta = getattr(client, metodo)(f"{ADMIN}{caminho}", **({"json": corpo} if corpo is not None else {}))
        assert resposta.status_code in (401, 403), (metodo, caminho, resposta.status_code)


# ============================================================ venda, nota fiscal e conciliação =========================================


def test_compra_e_bloqueada_sem_emissor_fiscal_ou_sem_dados_fiscais_do_cliente(client, db_session):
    cenario(db_session)
    catalogo(db_session)
    pagamento, prov = StubPaymentProvider(), ProvedorPago()
    base = dict(aceite_expiracao=True, payment_provider=pagamento, email_pagador="a@b.com", provider=prov, ator_id="1", agora=AGORA)
    # emissor desativado (o único adaptador de produção hoje) e cadastro sem CNPJ: dois motivos, nada é cobrado
    erro = pytest.raises(PesquisaBloqueada, pacotes.iniciar_compra, db_session, A, "ENRIQ_400", fiscal=FiscalDesativado(), **base)
    assert {b["codigo"] for b in erro.value.bloqueios} == {"fiscal_nao_configurado", "dados_fiscais_incompletos"}
    assert pagamento._preferencias == {} and db_session.query(EnriquecimentoCompra).count() == 0
    dados_fiscais(db_session, A)
    erro = pytest.raises(PesquisaBloqueada, pacotes.iniciar_compra, db_session, A, "ENRIQ_400", fiscal=FiscalDesativado(), **base)
    assert [b["codigo"] for b in erro.value.bloqueios] == ["fiscal_nao_configurado"]
    pacotes.iniciar_compra(db_session, A, "ENRIQ_400", fiscal=StubFiscalProvider(), **base)  # com emissor e dados, a compra segue


def test_catalogo_do_tenant_informa_que_a_compra_depende_da_nota_fiscal(client, db_session, prov_api):
    liberar_lusha(db_session)
    catalogo(db_session)
    app.dependency_overrides[get_fiscal_provider] = lambda: FiscalDesativado()
    d = client.get(f"{URL}/pacotes").json()
    assert d["compra_disponivel"] is False and [m["codigo"] for m in d["motivos"]] == ["fiscal_nao_configurado"]
    resposta = client.post(f"{URL}/compras", json={"pacote": "ENRIQ_400", "aceite_expiracao": True})
    assert resposta.status_code == 409 and resposta.json()["codigo"] == "fiscal_nao_configurado"
    app.dependency_overrides[get_fiscal_provider] = lambda: StubFiscalProvider()
    assert client.get(f"{URL}/pacotes").json()["compra_disponivel"] is True


def test_venda_aprovada_emite_nota_registra_o_que_o_provedor_informou_e_fica_conciliada(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    fiscal = StubFiscalProvider()
    compra, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), fiscal, taxas=31.19, liquido=508.81)
    assert compra.status == "APROVADA" and compra.status_pagamento_externo == "approved"
    assert (compra.valor_pago_brl, compra.taxa_pagamento_brl, compra.valor_liquido_brl) == (Decimal("540.00"), Decimal("31.19"), Decimal("508.81"))
    nota = db_session.query(EnriquecimentoNotaFiscal).filter_by(compra_id=compra.id).one()
    assert (nota.status, nota.numero, nota.tentativas, nota.provedor_fiscal) == ("EMITIDA", "1", 1, "stub") and nota.valor_brl == Decimal("540.00")
    dado = fiscal.chamadas[0]
    assert (dado.tomador_cnpj, dado.valor_brl, dado.chave_idempotencia) == ("11222333000181", Decimal("540.00"), f"enriquecimento-compra-{compra.id}")
    [venda] = vendas.listar_vendas(db_session, A)
    assert venda["situacao"] == "conciliada" and venda["nota"]["numero"] == "1" and venda["taxa_pagamento_brl"] == "31.19"
    resumo = vendas.resumo_conciliacao(db_session)
    assert resumo["por_situacao"] == {"conciliada": 1} and (resumo["bruto_brl"], resumo["taxas_informadas_brl"], resumo["liquido_informado_brl"]) == ("540.00", "31.19", "508.81")


def test_taxas_nao_informadas_pelo_provedor_ficam_vazias_e_nunca_sao_estimadas(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    compra, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    assert compra.taxa_pagamento_brl is None and compra.valor_liquido_brl is None
    assert vendas.resumo_conciliacao(db_session)["taxas_informadas_brl"] == "0.00"


def test_falha_do_emissor_nao_desfaz_o_credito_pago_e_a_nota_pode_ser_reemitida_sem_duplicar(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    fiscal = StubFiscalProvider(fora_do_ar_vezes=1)
    compra, pagamento_id = comprar(db_session, StubPaymentProvider(), ProvedorPago(), fiscal)
    assert compra.status == "APROVADA" and ledger.composicao(db_session, A, AGORA)["adicional_restante"] == 400  # o crédito pago permanece
    nota = db_session.query(EnriquecimentoNotaFiscal).filter_by(compra_id=compra.id).one()
    assert (nota.status, nota.tentativas) == ("FALHA", 1) and "fora do ar" in nota.erro
    assert vendas.listar_vendas(db_session, A)[0]["situacao"] == "nota_com_falha"
    nota = vendas.emitir_nota(db_session, compra.id, fiscal, ator_id="1")
    assert (nota.status, nota.numero, nota.tentativas, nota.erro) == ("EMITIDA", "1", 2, None)
    vendas.emitir_nota(db_session, compra.id, fiscal, ator_id="1")  # já emitida: não chama o emissor de novo
    assert len(fiscal.chamadas) == 2 and db_session.query(EnriquecimentoNotaFiscal).count() == 1
    assert vendas.listar_vendas(db_session, A)[0]["situacao"] == "conciliada"


def test_novo_aviso_do_provedor_de_pagamento_reemite_a_nota_que_ficou_pendente(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    pagamento, fiscal = StubPaymentProvider(), StubFiscalProvider(fora_do_ar_vezes=1)
    compra, pagamento_id = comprar(db_session, pagamento, ProvedorPago(), fiscal)
    assert db_session.query(EnriquecimentoNotaFiscal).one().status == "FALHA"
    pacotes.confirmar_via_webhook(db_session, pagamento, pagamento_id, AGORA, fiscal=fiscal)  # reenvio do aviso
    assert db_session.query(EnriquecimentoNotaFiscal).one().status == "EMITIDA"
    assert db_session.query(EnriquecimentoMovimento).filter_by(tipo="COMPRA").count() == 1  # crédito concedido uma única vez


def test_emissor_que_rejeita_os_dados_deixa_a_nota_com_falha_e_o_motivo(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    compra, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider(rejeitar="CNPJ do tomador inválido"))
    nota = db_session.query(EnriquecimentoNotaFiscal).one()
    assert nota.status == "FALHA" and nota.erro == "CNPJ do tomador inválido" and compra.status == "APROVADA"


def test_sem_emissor_no_webhook_a_venda_aparece_como_paga_sem_nota(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    compra, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    db_session.query(EnriquecimentoNotaFiscal).delete()
    db_session.commit()
    assert vendas.listar_vendas(db_session, A)[0]["situacao"] == "pago_sem_nota"


def test_situacao_de_conciliacao_e_derivada_dos_fatos_registrados():
    compra = EnriquecimentoCompra(status="APROVADA", preco_total_brl=Decimal("540.00"), valor_pago_brl=Decimal("540.00"))
    emitida = EnriquecimentoNotaFiscal(status="EMITIDA")
    assert vendas.situacao(compra, emitida) == "conciliada"
    assert vendas.situacao(compra, None) == "pago_sem_nota" and vendas.situacao(compra, EnriquecimentoNotaFiscal(status="FALHA")) == "nota_com_falha"
    assert vendas.situacao(EnriquecimentoCompra(status="APROVADA", preco_total_brl=Decimal("540.00"), valor_pago_brl=Decimal("500.00")), emitida) == "divergente"
    assert vendas.situacao(EnriquecimentoCompra(status="APROVADA", preco_total_brl=Decimal("540.00")), emitida) == "divergente"  # pagamento não informado
    assert vendas.situacao(EnriquecimentoCompra(status="APROVADA", preco_total_brl=Decimal("540.00"), valor_pago_brl=Decimal("540.00"),
                                                contestacao_status="charged_back"), emitida) == "contestada"
    assert vendas.situacao(compra, emitida, estornada=True) == "estornada"
    assert vendas.situacao(EnriquecimentoCompra(status="PENDENTE"), None) == "aguardando_pagamento"
    assert vendas.situacao(EnriquecimentoCompra(status="REJEITADA"), None) == "pagamento_rejeitado"


# ============================================================ contestação e estorno manual =============================================


@pytest.mark.parametrize("status_externo", ["refunded", "charged_back", "cancelled"])
def test_reembolso_ou_chargeback_avisado_pelo_provedor_so_sinaliza_e_nao_mexe_nos_creditos(client, db_session, status_externo):
    liberar_lusha(db_session)
    catalogo(db_session)
    pagamento, fiscal = StubPaymentProvider(), StubFiscalProvider()
    compra, pagamento_id = comprar(db_session, pagamento, ProvedorPago(), fiscal)
    antes = (ledger.saldo(db_session, A), db_session.query(EnriquecimentoMovimento).count())
    pagamento._preferencias[compra.preferencia_id_externo]["status"] = status_externo
    for _ in range(2):  # o aviso chega repetido
        pacotes.confirmar_via_webhook(db_session, pagamento, pagamento_id, AGORA, fiscal=fiscal)
    db_session.refresh(compra)
    assert compra.status == "APROVADA" and compra.contestacao_status == status_externo and compra.contestado_em == AGORA
    assert (ledger.saldo(db_session, A), db_session.query(EnriquecimentoMovimento).count()) == antes  # nenhum estorno automático
    assert db_session.query(EnriquecimentoEstornoCompra).count() == 0
    assert db_session.query(AuditLog).filter_by(evento_tipo="enriquecimento_compra_contestada").count() == 1
    assert vendas.listar_vendas(db_session, A)[0]["situacao"] == "contestada"


def test_estorno_manual_exige_justificativa_evidencia_e_compra_paga(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    pendente, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider(), pagar=False)
    base = dict(tipo="ESTORNO", creditos=100, justificativa="Cliente pediu o cancelamento da compra", evidencia="protocolo-123", ator_id="10", tenant_auditoria=A)
    with pytest.raises(ValidacaoFalhou, match="pagamento aprovado"):
        estornos.solicitar(db_session, pendente.id, **base)
    paga, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    for campos, trecho in ((dict(tipo="OUTRO"), "tipo"), (dict(creditos=0), "inteiro positivo"), (dict(justificativa="curta"), "justificativa"),
                           (dict(evidencia=""), "evidência"), (dict(creditos=401), "excede o total")):
        with pytest.raises(ValidacaoFalhou, match=trecho):
            estornos.solicitar(db_session, paga.id, **{**base, **campos})
    pedido = estornos.solicitar(db_session, paga.id, **base)
    assert pedido.status == "SOLICITADO" and ledger.composicao(db_session, A, AGORA)["adicional_restante"] == 400  # pedir não reverte nada
    with pytest.raises(ValidacaoFalhou, match="em andamento"):
        estornos.solicitar(db_session, paga.id, **base)


def test_estorno_manual_aprovado_por_outro_administrador_gera_lancamento_compensatorio_idempotente(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    paga, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    original = db_session.query(EnriquecimentoMovimento).filter_by(tipo="COMPRA").one()
    pedido = estornos.solicitar(db_session, paga.id, tipo="CHARGEBACK", creditos=400, justificativa="Contestação do titular do cartão", evidencia="chargeback-9981",
                                ator_id="10", tenant_auditoria=A)
    with pytest.raises(NaoAutorizado, match="não pode aprová-lo"):
        estornos.decidir(db_session, pedido.id, aprovar=True, motivo="aprovado", ator_id="10", tenant_auditoria=A)  # quem pediu não decide
    assert db_session.get(EnriquecimentoEstornoCompra, pedido.id).status == "SOLICITADO"
    feito = estornos.decidir(db_session, pedido.id, aprovar=True, motivo="Chargeback confirmado no extrato", ator_id="11", tenant_auditoria=A, agora=AGORA)
    assert (feito.status, feito.creditos_revertidos, feito.creditos_ja_consumidos, feito.decidido_por) == ("EXECUTADO", 400, 0, "11")
    movimento = db_session.get(EnriquecimentoMovimento, feito.movimento_id)
    assert (movimento.tipo, movimento.delta_saldo, movimento.origem, movimento.idempotency_key) == ("ESTORNO_COMPRA", -400, "compra", f"estorno-compra:{pedido.id}")
    assert db_session.get(EnriquecimentoMovimento, original.id).delta_saldo == 400  # o crédito original nunca é apagado nem alterado
    assert ledger.composicao(db_session, A, AGORA)["adicional_restante"] == 0 and ledger.saldo(db_session, A) == 0
    for _ in range(2):  # retry/duplicidade: não debita de novo
        estornos.decidir(db_session, pedido.id, aprovar=True, motivo="repetição do mesmo callback", ator_id="11", tenant_auditoria=A, agora=AGORA)
    assert db_session.query(EnriquecimentoMovimento).filter_by(tipo="ESTORNO_COMPRA").count() == 1
    assert vendas.listar_vendas(db_session, A)[0]["situacao"] == "estornada"
    eventos = {e.evento_tipo for e in db_session.query(AuditLog).all()}
    assert {"enriquecimento_estorno_solicitado", "enriquecimento_estorno_executado"} <= eventos
    invariantes(db_session)


def test_estorno_so_reverte_o_que_nao_foi_consumido_e_registra_o_resto(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    cfg, _ = config.config_vigente(db_session, A)
    ledger.preparar(db_session, A, cfg, AGORA)
    paga, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    ledger.travar_carteira(db_session, A)
    ledger.lancar(db_session, A, "CONSUMO", delta_saldo=-100, agora=AGORA)  # 30 da franquia + 70 do adicional
    db_session.commit()
    assert ledger.composicao(db_session, A, AGORA)["adicional_restante"] == 330
    pedido = estornos.solicitar(db_session, paga.id, tipo="ESTORNO", creditos=400, justificativa="Cancelamento dentro do prazo de arrependimento", evidencia="e-mail-55",
                                ator_id="10", tenant_auditoria=A)
    feito = estornos.decidir(db_session, pedido.id, aprovar=True, motivo="Aprovado pelo financeiro", ator_id="11", tenant_auditoria=A, agora=AGORA)
    assert (feito.creditos_revertidos, feito.creditos_ja_consumidos) == (330, 70)
    assert ledger.saldo(db_session, A) == 0  # nada fica negativo: o consumo já feito não volta
    invariantes(db_session)


def test_estorno_parcial_nao_causa_expiracao_em_dobro_no_mes_seguinte(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    cfg, _ = config.config_vigente(db_session, A)
    ledger.preparar(db_session, A, cfg, AGORA)
    paga, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    pedido = estornos.solicitar(db_session, paga.id, tipo="AJUSTE", creditos=100, justificativa="Ajuste comercial acordado com o cliente", evidencia="ata-12",
                                ator_id="10", tenant_auditoria=A)
    estornos.decidir(db_session, pedido.id, aprovar=True, motivo="Aprovado", ator_id="11", tenant_auditoria=A, agora=AGORA)
    assert ledger.saldo(db_session, A) == 330  # 30 de franquia + 300 que sobraram do pacote
    ledger.preparar(db_session, A, cfg, datetime(2026, 11, 2, 12, 0))
    db_session.commit()
    assert ledger.saldo(db_session, A) == 30  # venceu tudo de outubro (franquia 30 + pacote 300) uma única vez; entrou só a franquia de novembro
    expirado = sum(-m.delta_saldo for m in db_session.query(EnriquecimentoMovimento).filter_by(tipo="EXPIRACAO").all())
    assert expirado == 330
    invariantes(db_session)


def test_estorno_rejeitado_nao_mexe_no_razao_e_nao_pode_ser_aprovado_depois(client, db_session):
    liberar_lusha(db_session)
    catalogo(db_session)
    paga, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    pedido = estornos.solicitar(db_session, paga.id, tipo="ESTORNO", creditos=50, justificativa="Pedido sem comprovação do cliente", evidencia="ticket-1",
                                ator_id="10", tenant_auditoria=A)
    rejeitado = estornos.decidir(db_session, pedido.id, aprovar=False, motivo="Sem evidência suficiente", ator_id="11", tenant_auditoria=A)
    assert rejeitado.status == "REJEITADO" and db_session.query(EnriquecimentoMovimento).filter_by(tipo="ESTORNO_COMPRA").count() == 0
    with pytest.raises(ValidacaoFalhou, match="já foi decidido"):
        estornos.decidir(db_session, pedido.id, aprovar=True, motivo="mudei de ideia", ator_id="12", tenant_auditoria=A)
    estornos.solicitar(db_session, paga.id, tipo="ESTORNO", creditos=50, justificativa="Novo pedido com a evidência anexada", evidencia="ticket-2", ator_id="10",
                       tenant_auditoria=A)  # um novo pedido pode ser aberto


def test_a_trava_dos_quatro_olhos_pode_ser_desligada_so_por_configuracao_do_ambiente(client, db_session, monkeypatch):
    liberar_lusha(db_session)
    catalogo(db_session)
    paga, _ = comprar(db_session, StubPaymentProvider(), ProvedorPago(), StubFiscalProvider())
    pedido = estornos.solicitar(db_session, paga.id, tipo="ESTORNO", creditos=10, justificativa="Ajuste pequeno a pedido do cliente", evidencia="ticket-9",
                                ator_id="10", tenant_auditoria=A)
    monkeypatch.setattr(settings, "enriquecimento_estorno_exige_segundo_aprovador", False)
    assert estornos.decidir(db_session, pedido.id, aprovar=True, motivo="Equipe com um único administrador", ator_id="10", tenant_auditoria=A,
                            agora=AGORA).status == "EXECUTADO"


def test_api_de_vendas_nota_e_estorno_manual(client, db_session, prov_api):
    liberar_lusha(db_session)
    catalogo(db_session)
    fiscal = StubFiscalProvider(fora_do_ar_vezes=1)
    app.dependency_overrides[get_fiscal_provider] = lambda: fiscal
    pagamento = StubPaymentProvider()
    app.dependency_overrides[get_payment_provider] = lambda: pagamento
    compra, _ = comprar(db_session, pagamento, prov_api, fiscal)
    vendas_api = client.get(f"{ADMIN}/vendas").json()
    assert vendas_api["vendas"][0]["situacao"] == "nota_com_falha" and vendas_api["resumo"]["por_situacao"] == {"nota_com_falha": 1}
    reemitida = client.post(f"{ADMIN}/compras/{compra.id}/emitir-nota")
    assert reemitida.status_code == 200 and reemitida.json()["status"] == "EMITIDA" and reemitida.json()["numero"] == "1"
    # a lista do tenant mostra o pedido com a nota e a situação
    minha = client.get(f"{URL}/compras").json()[0]
    assert minha["situacao"] == "conciliada" and minha["nota"]["numero"] == "1"
    # estorno: o usuário de teste (super_admin 1) solicita; ele mesmo não decide; outro super_admin decide
    pedido = client.post(f"{ADMIN}/compras/{compra.id}/estornos", json={"tipo": "ESTORNO", "creditos": 100, "justificativa": "Cliente pediu o cancelamento da compra",
                                                                        "evidencia": "protocolo-77"})
    assert pedido.status_code == 201 and pedido.json()["status"] == "SOLICITADO"
    eid = pedido.json()["id"]
    assert client.post(f"{ADMIN}/estornos/{eid}/decidir", json={"aprovar": True, "motivo": "aprovado por mim mesmo"}).status_code == 403
    outro = Usuario(id=77, tenant_id=A, papel="super_admin", nome="Segundo", email="segundo@x.com", ativo=True)
    app.dependency_overrides[get_usuario_atual] = lambda: outro
    feito = client.post(f"{ADMIN}/estornos/{eid}/decidir", json={"aprovar": True, "motivo": "Confirmado com o financeiro"})
    assert feito.status_code == 200 and feito.json()["status"] == "EXECUTADO" and feito.json()["creditos_revertidos"] == 100
    assert [e["status"] for e in client.get(f"{ADMIN}/estornos?status=EXECUTADO").json()] == ["EXECUTADO"]
    assert ledger.composicao(db_session, A)["adicional_restante"] == 300
    eventos = {a["evento"] for a in client.get(f"{ADMIN}/auditoria").json()}
    assert {"enriquecimento_nota_falhou", "enriquecimento_nota_emitida", "enriquecimento_estorno_solicitado", "enriquecimento_estorno_executado",
            "enriquecimento_compra_confirmada"} <= eventos


def test_painel_do_tenant_reflete_o_estorno_no_saldo_adicional(client, db_session, prov_api):
    liberar_lusha(db_session)
    catalogo(db_session)
    paga, _ = comprar(db_session, StubPaymentProvider(), prov_api, StubFiscalProvider())
    pedido = estornos.solicitar(db_session, paga.id, tipo="ESTORNO", creditos=150, justificativa="Cancelamento solicitado pelo cliente", evidencia="ticket-3",
                                ator_id="10", tenant_auditoria=A)
    estornos.decidir(db_session, pedido.id, aprovar=True, motivo="Aprovado", ator_id="11", tenant_auditoria=A, agora=config.agora_utc())
    d = client.get(f"{URL}/painel").json()
    assert d["composicao"]["adicional_restante"] == 250 and d["compra_adicional"]["disponivel"] is True
    extrato = client.get(f"{URL}/movimentacoes?tipo=ESTORNO_COMPRA").json()
    assert [m["delta_saldo"] for m in extrato] == [-150]
    assert painel.auditoria_administrativa(db_session, prefixo="enriquecimento_estorno")
