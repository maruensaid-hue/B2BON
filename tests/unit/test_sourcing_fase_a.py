"""Phase A (plano unificado §37): fundação do processo canônico.

- os 11 tipos de processo universais (§5) existem no vocabulário do núcleo;
- ruleset traz versão, vigência, fonte e configuração (§22);
- workflow e ruleset são decididos num lugar só por (lado, segmento, tipo) (§21),
  e cada combinação que os lados produzem hoje resolve para o mesmo fluxo de antes.
"""

from datetime import date

import pytest

from app.contexts.bids import contract as bids
from app.contexts.bids import fluxo as fluxo_venda
from app.contexts.procurement import fluxo as fluxo_compra
from app.contexts.sourcing import contract as sourcing

Lado, Segmento = sourcing.tipos.Lado, sourcing.tipos.Segmento
TIPOS_UNIVERSAIS = {"PUBLIC_TENDER", "RFP", "RFI", "RFQ", "EOI", "PRIVATE_TENDER", "DIRECT_AWARD", "PRICE_REGISTRATION",
                    "FRAMEWORK_AGREEMENT", "VENDOR_QUALIFICATION", "STRATEGIC_SOURCING_EVENT"}


def test_tipos_de_processo_universais():
    assert set(sourcing.tipos.TIPOS_PROCESSO) == TIPOS_UNIVERSAIS


def test_ruleset_registra_versao_vigencia_fonte_e_configuracao():
    lei = sourcing.ruleset.obter("PUBLIC_PROCUREMENT_BR_14133@1")
    assert lei.versao == 1 and lei.vigente_desde == date(2021, 4, 1) and "14.133" in lei.fonte
    assert set(lei.parametros) == {"dias_alerta_contrato", "desvio_orcamento", "desvio_alerta_preco", "limite_fragmentacao"}
    privado = sourcing.ruleset.obter("PRIVATE_RFP@1")
    assert privado.vigente_desde is None and privado.fonte
    with pytest.raises(ValueError, match="fonte"):
        sourcing.ruleset.Ruleset("SEM_FONTE@1", "x", " ")


def test_toda_modalidade_resolve_pelo_ponto_central_com_o_fluxo_de_antes():
    for modalidade in (*bids.tipos.MODALIDADES, None):
        segmento, tipo = fluxo_venda.classificar(modalidade)
        workflow, regras = sourcing.workflow.resolver(Lado.VENDA, segmento, tipo)
        privada = modalidade is not None and modalidade.startswith("PRIVATE_")
        esperado = ("ENTERPRISE_RFP_SELL@2", "PRIVATE_RFP@1") if privada else ("PUBLIC_TENDER_SELL@1", None)
        assert (workflow.codigo, regras.codigo if regras else None) == esperado, modalidade
        assert tipo in sourcing.tipos.TIPOS_PROCESSO
    for modalidade in (*sourcing.tipos.TIPOS_PROCESSO, None, "MODALIDADE_ANTIGA"):
        workflow, regras = fluxo_compra.configuracao(modalidade)
        assert (workflow.codigo, regras.codigo) == ("PUBLIC_PROCUREMENT_BUY@1", "PUBLIC_PROCUREMENT_BR_14133@1")


def test_sem_vinculo_falha_fechado(monkeypatch):
    """Sem vínculo não há fluxo por omissão (desde a Phase E todos os lados e segmentos têm vínculo)."""
    monkeypatch.setattr(sourcing.workflow, "_VINCULOS", {})
    with pytest.raises(LookupError):
        sourcing.workflow.resolver(Lado.COMPRA, Segmento.EMPRESA, "RFP")


def test_vinculo_confere_lado_tipo_e_nao_e_sobrescrito():
    venda = sourcing.workflow.obter("PUBLIC_TENDER_SELL@1")
    with pytest.raises(ValueError, match="lado"):
        sourcing.workflow.vincular(Lado.COMPRA, Segmento.PUBLICO, venda)
    with pytest.raises(ValueError, match="desconhecido"):
        sourcing.workflow.vincular(Lado.VENDA, Segmento.PUBLICO, venda, tipos_processo=("INVENTADO",))
    with pytest.raises(ValueError, match="já vinculado"):
        sourcing.workflow.vincular(Lado.VENDA, Segmento.PUBLICO, sourcing.workflow.obter("ENTERPRISE_RFP_SELL@1"))
    sourcing.workflow.vincular(Lado.VENDA, Segmento.PUBLICO, venda)  # mesmo vínculo: idempotente


def test_vinculo_por_tipo_vence_o_do_segmento(monkeypatch):
    monkeypatch.setattr(sourcing.workflow, "_VINCULOS", dict(sourcing.workflow.vinculos()))
    T = sourcing.workflow.Transicao
    rfq = sourcing.workflow.Workflow("TESTE_RFQ_SELL@1", Lado.VENDA, ("A",), "A", (), (T("A", "status"),))
    monkeypatch.setattr(sourcing.workflow, "_REGISTRO", dict(sourcing.workflow._REGISTRO))
    sourcing.workflow.vincular(Lado.VENDA, Segmento.PUBLICO, rfq, tipos_processo=("RFQ",))
    assert sourcing.workflow.resolver(Lado.VENDA, Segmento.PUBLICO, "RFQ")[0] is rfq
    assert sourcing.workflow.resolver(Lado.VENDA, Segmento.PUBLICO, "RFP")[0].codigo == "PUBLIC_TENDER_SELL@1"


def test_versao_vem_do_codigo():
    assert sourcing.workflow.obter("PUBLIC_PROCUREMENT_BUY@1").versao == 1
