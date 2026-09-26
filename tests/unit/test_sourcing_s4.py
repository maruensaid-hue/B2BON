"""Sourcing S4: workflow e rulesets declarativos no lugar das tuplas.

Critério da S4: as transições atuais são reproduzidas. O comportamento de
antes da S4 está copiado aqui (`_legado_*`) e cada combinação (estado de
origem, estado de destino, ação) é comparada com o workflow declarativo:
mesmo aceite, mesma exceção, mesma mensagem.
"""

import pytest

from app.contexts.bids import contract as bids
from app.contexts.bids import espelho as espelho_venda
from app.contexts.procurement import contract as procurement
from app.contexts.procurement import espelho as espelho_compra
from app.contexts.sourcing import contract as sourcing
from app.models.licitacao import Licitacao
from app.models.processo_contratacao import ProcessoContratacao
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

# --- Retrato do código anterior à S4 (não mudar) ------------------------------------
LEGADO_STATUS_LICITACAO = ("IDENTIFICADA", "EM_ANALISE", "GO", "NO_GO", "PROPOSTA_ENVIADA", "GANHA", "PERDIDA", "CANCELADA")
LEGADO_FINAIS_LICITACAO = ("NO_GO", "GANHA", "PERDIDA", "CANCELADA")
LEGADO_STATUS_PROCESSO = ("PLANEJAMENTO", "ESTUDOS_TECNICOS", "TERMO_REFERENCIA", "PESQUISA_PRECOS", "APROVACAO", "PUBLICADO",
                          "SELECAO", "HOMOLOGADO", "CONTRATADO", "FRACASSADO", "CANCELADO")
LEGADO_FINAIS_PROCESSO = ("CONTRATADO", "FRACASSADO", "CANCELADO")
LEGADO_DOCUMENTOS = {
    "TERMO_REFERENCIA": ("ETP",), "PESQUISA_PRECOS": ("ETP", "TR"), "APROVACAO": ("ETP", "TR", "PESQUISA_PRECO"),
    "PUBLICADO": ("ETP", "TR", "PESQUISA_PRECO", "EDITAL"),
}


def _legado_licitacao(para: str, acao: str):
    """`mudar_status` (ação status), `decidir` (go_no_go) e `registrar_resultado` (resultado) antes da S4:
    nenhuma restrição de origem."""
    if acao == "status":
        if para not in LEGADO_STATUS_LICITACAO:
            return ValidacaoFalhou, f"Status inválido: {para}"
        if para in ("GO", "NO_GO"):
            return RegraNegocioViolada, "GO/NO_GO é registrado pela decisão Go/No-Go, com a recomendação e a justificativa."
        if para in ("GANHA", "PERDIDA"):
            return RegraNegocioViolada, "Use o registro de resultado para informar vencedor e valor."
    return None


def _legado_processo(para: str):
    """`cadastros.atualizar` antes da S4: qualquer etapa válida, de qualquer etapa."""
    return None if para in LEGADO_STATUS_PROCESSO else (ValidacaoFalhou, f"Status inválido: {para}")


def _resultado(funcao):
    try:
        funcao()
    except (ValidacaoFalhou, RegraNegocioViolada) as erro:
        return type(erro), str(erro)
    return None


ORIGENS_LICITACAO = (*LEGADO_STATUS_LICITACAO, None, "STATUS_ANTIGO_FORA_DO_FLUXO")
# `decidir` recusa antes qualquer decisão fora de GO/NO_GO; `registrar_resultado` só produz GANHA/PERDIDA.
DESTINOS = {"status": (*LEGADO_STATUS_LICITACAO, "INVENTADO"), "go_no_go": ("GO", "NO_GO"), "resultado": ("GANHA", "PERDIDA")}


@pytest.mark.parametrize("codigo", ["PUBLIC_TENDER_SELL@1", "ENTERPRISE_RFP_SELL@1"])
def test_workflow_de_venda_reproduz_todas_as_transicoes_anteriores(codigo):
    fluxo = sourcing.workflow.obter(codigo)
    assert fluxo.estados == LEGADO_STATUS_LICITACAO and fluxo.finais == LEGADO_FINAIS_LICITACAO
    assert fluxo.inicial == "IDENTIFICADA" and fluxo.lado == sourcing.tipos.Lado.VENDA
    combinacoes = 0
    for acao, destinos in DESTINOS.items():
        for de in ORIGENS_LICITACAO:
            for para in destinos:
                combinacoes += 1
                obtido = _resultado(lambda: fluxo.validar(para, acao, de=de))  # noqa: B023
                assert obtido == _legado_licitacao(para, acao), (codigo, de, para, acao)
    assert combinacoes == 10 * 9 + 10 * 2 + 10 * 2


def test_workflow_de_compra_reproduz_todas_as_transicoes_anteriores():
    fluxo = sourcing.workflow.obter("PUBLIC_PROCUREMENT_BUY@1")
    assert fluxo.estados == LEGADO_STATUS_PROCESSO and fluxo.finais == LEGADO_FINAIS_PROCESSO and fluxo.inicial == "PLANEJAMENTO"
    for de in (*LEGADO_STATUS_PROCESSO, None, "ETAPA_ANTIGA"):
        for para in (*LEGADO_STATUS_PROCESSO, "INVENTADA"):
            assert _resultado(lambda: fluxo.validar(para, "status", de=de)) == _legado_processo(para), (de, para)  # noqa: B023


def test_aliases_derivam_do_workflow_e_do_ruleset():
    assert bids.tipos.STATUS_LICITACAO == LEGADO_STATUS_LICITACAO and bids.tipos.STATUS_FINAIS == LEGADO_FINAIS_LICITACAO
    assert procurement.tipos.STATUS_PROCESSO == LEGADO_STATUS_PROCESSO
    assert procurement.tipos.STATUS_PROCESSO_FINAIS == LEGADO_FINAIS_PROCESSO
    assert procurement.tipos.DOCUMENTOS_ESPERADOS == LEGADO_DOCUMENTOS
    assert procurement.cadastros.STATUS_VALIDOS["processo_contratacao"] == LEGADO_STATUS_PROCESSO
    assert procurement.cadastros.STATUS_INICIAL["processo_contratacao"] == "PLANEJAMENTO"


def test_ruleset_14133_reproduz_as_constantes_e_a_configuracao_por_orgao():
    regras = sourcing.ruleset.obter("PUBLIC_PROCUREMENT_BR_14133@1")
    assert {etapa: regras.documentos(etapa) for etapa in LEGADO_DOCUMENTOS} == LEGADO_DOCUMENTOS
    assert regras.documentos("PLANEJAMENTO") == ()
    assert procurement.riscos.DIAS_CONTRATO == 120 and procurement.riscos.DESVIO_ORCAMENTO == 0.2
    assert procurement.precos.DESVIO_ALERTA == 0.30
    assert regras.parametro("dias_alerta_contrato", {"dias_alerta_contrato": 30}) == 30
    assert regras.parametro("dias_alerta_contrato", None) == 120
    # sem padrão: sem configuração, o sinal fica sem avaliação (nunca um limite inventado)
    assert regras.parametro("limite_fragmentacao", {}) is None
    assert regras.parametro("limite_fragmentacao", {"limite_fragmentacao": 50000}) == 50000
    with pytest.raises(KeyError):
        regras.parametro("parametro_inexistente")


def test_ruleset_do_rfp_privado_nao_tem_regra_regulatoria():
    regras = sourcing.ruleset.obter("PRIVATE_RFP@1")
    assert regras.documentos_esperados == {} and regras.parametros == {}


def test_espelho_so_grava_codigos_registrados():
    """Todo workflow/ruleset gravado nas tabelas unificadas existe no registro."""
    codigos = []
    for modalidade in (*bids.tipos.MODALIDADES, None):
        valores = espelho_venda.processo(Licitacao(tenant_id="t", titulo="x", modalidade=modalidade, status="IDENTIFICADA"))
        codigos.append((valores["workflow"], valores["ruleset"]))
    valores = espelho_compra.processo(ProcessoContratacao(tenant_id="t", objeto="x", status="PLANEJAMENTO"))
    codigos.append((valores["workflow"], valores["ruleset"]))
    for workflow, ruleset in codigos:
        assert workflow in sourcing.workflow.codigos()
        assert ruleset is None or ruleset in sourcing.ruleset.codigos()
    assert ("ENTERPRISE_RFP_SELL@2", "PRIVATE_RFP@1") in codigos  # Phase C: v2 (com negociação)
    assert ("PUBLIC_TENDER_SELL@1", None) in codigos
    assert ("PUBLIC_PROCUREMENT_BUY@1", "PUBLIC_PROCUREMENT_BR_14133@1") in codigos


def test_lado_do_workflow_bate_com_o_lado_que_o_grava():
    assert sourcing.workflow.obter("PUBLIC_TENDER_SELL@1").lado == espelho_venda.LADO
    assert sourcing.workflow.obter("PUBLIC_PROCUREMENT_BUY@1").lado == espelho_compra.LADO


def test_definicao_invalida_ou_versao_reescrita_e_recusada():
    T, W = sourcing.workflow.Transicao, sourcing.workflow.Workflow
    with pytest.raises(ValueError, match="não declarados"):
        W("X@1", sourcing.tipos.Lado.VENDA, ("A",), "A", ("B",), (T("A", "status"),))
    with pytest.raises(ValueError, match="versão"):
        W("SEM_VERSAO", sourcing.tipos.Lado.VENDA, ("A",), "A", (), (T("A", "status"),))
    atual = sourcing.workflow.obter("PUBLIC_TENDER_SELL@1")
    with pytest.raises(ValueError, match="nova versão"):
        sourcing.workflow.registrar(W("PUBLIC_TENDER_SELL@1", atual.lado, atual.estados, atual.inicial, atual.finais, ()))
    assert sourcing.workflow.registrar(atual) is atual  # mesma definição: idempotente
    with pytest.raises(ValueError, match="nova versão"):
        sourcing.ruleset.registrar(sourcing.ruleset.Ruleset("PRIVATE_RFP@1", "outra", "fonte", parametros={"x": 1}))


def test_restricao_de_origem_e_suportada_pelo_motor():
    """Nenhum fluxo v1 restringe a origem (paridade); o motor já aceita para as próximas versões."""
    T = sourcing.workflow.Transicao
    fluxo = sourcing.workflow.Workflow("TESTE@1", sourcing.tipos.Lado.VENDA, ("A", "B", "C"), "A", ("C",),
                                       (T("B", "status", frozenset({"A"})), T("C", "status")))
    fluxo.validar("B", "status", de="A")
    with pytest.raises(RegraNegocioViolada, match="Transição não permitida: C → B"):
        fluxo.validar("B", "status", de="C")
