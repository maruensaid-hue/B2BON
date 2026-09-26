"""Plano de sourcing S1 (D-055): engines compartilhados por Sell e Buy.

- Requirement Engine: um laço, perfis diferentes (edital × RFP privado).
- Evaluation Engine: mesma regra de decisão nas duas direções.
- Matching Engine: estratégia de ICP com paridade com a fórmula anterior.
- Núcleo não conhece modelos de nenhum dos lados (não vira ponte Buy/Sell).
"""

import ast
import itertools
import json
from pathlib import Path

import pytest

from app.contexts.intelligence.contract import ContextoIA
from app.contexts.shared import matching
from app.contexts.sourcing import contract as sourcing
from app.models.creditos_ia import ExecucaoIa
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider

RAIZ = Path(__file__).resolve().parents[2]
PAGINAS = [
    "EDITAL 1/2026\n1. OBJETO: plataforma de atendimento.",
    "4.2 A contratada deve manter SLA de 99,5% de disponibilidade.\n5.1 Apresentar certificação ISO 27001.",
]
_SISTEMA_RFP = "Extraia requisitos de um RFP privado em JSON."
PERFIL_RFP = sourcing.requisitos.PerfilExtracao(
    nome="rfp_privado", sistema=_SISTEMA_RFP, categorias=("SLA", "SEGURANCA"), max_tokens=2000, caracteres_por_bloco=60)


class LLMRoteiro(FakeLLMProvider):
    def __init__(self, respostas):
        super().__init__()
        self.definir_respostas(respostas)


def _contexto():
    return ContextoIA(tenant_id="tenant-sourcing", feature="bids.analise_tr", entidade_tipo="documento", entidade_id=1)


def test_extrator_grava_so_o_que_esta_no_texto_e_calcula_a_pagina(db_session):
    resposta = json.dumps([
        {"categoria": "sla", "descricao": "SLA mínimo", "citacao": "SLA de 99,5% de disponibilidade", "clausula": "4.2", "pagina": 9},
        {"categoria": "SEGURANCA", "descricao": "ISO 27001", "citacao": "certificação ISO 27001", "clausula": "9.9"},
        {"categoria": "SEGURANCA", "descricao": "Inventado", "citacao": "SOC 2 Type II obrigatório"},
        {"categoria": "OUTRA", "descricao": "Fora do perfil", "citacao": "plataforma de atendimento"},
    ])
    llm = LLMRoteiro([resposta] * 3)
    extracao = sourcing.requisitos.extrair(db_session, llm, _contexto(), PAGINAS, PERFIL_RFP, "RFP teste")

    assert [(i.categoria, i.pagina, i.clausula) for i in extracao.itens] == [("SLA", 2, "4.2"), ("SEGURANCA", 2, None)]
    assert extracao.sem_evidencia >= 1  # a citação inventada não entra
    assert all(_SISTEMA_RFP in chamada.system for chamada in llm.chamadas)  # o perfil manda na instrução
    assert db_session.query(ExecucaoIa).count() == 1  # vários blocos, uma execução de crédito


def test_mesmo_extrator_serve_ao_perfil_do_edital(db_session):
    from app.contexts.bids import analise

    perfil = analise.perfil()
    assert perfil.nome == "edital_tr" and "HABILITACAO" in perfil.categorias
    llm = LLMRoteiro([json.dumps([{"categoria": "CERTIFICACAO", "descricao": "ISO", "citacao": "certificação ISO 27001"}])])
    extracao = sourcing.requisitos.extrair(db_session, llm, _contexto(), PAGINAS, perfil, "EDITAL")
    assert [(i.categoria, i.pagina) for i in extracao.itens] == [("CERTIFICACAO", 2)]


def test_documento_restrito_ou_sem_texto_nao_vai_para_ia():
    with pytest.raises(RegraNegocioViolada, match="RESTRICTED"):
        sourcing.documentos.exigir_analisavel("PENDENTE", "RESTRICTED")
    with pytest.raises(RegraNegocioViolada, match="OCR"):
        sourcing.documentos.exigir_analisavel("SEM_TEXTO")
    sourcing.documentos.exigir_analisavel("PENDENTE", "CONFIDENTIAL")
    assert sourcing.documentos.preparar(b"   \f  ", "text/plain").status_inicial == "SEM_TEXTO"
    arquivo = sourcing.documentos.preparar("a\fb".encode(), "text/plain")
    assert (arquivo.paginas, arquivo.status_inicial, len(arquivo.sha256)) == (["a", "b"], "PENDENTE", 64)


def test_avaliacao_na_direcao_da_proposta_com_as_mesmas_regras_de_decisao():
    """Buy: "esta proposta atende?" — o motor é o mesmo da matriz do vendedor."""
    proposta = {"sla": "99,9%", "certificacoes": []}
    Decisao = sourcing.avaliacao.Decisao

    def sla(req):
        if req["categoria"] != "SLA":
            return None
        return Decisao("COMPLIANT", f"Proposta oferece {proposta['sla']}.", [{"tipo": "proposta", "campo": "sla"}])

    def certificacao(req):
        if req["categoria"] != "CERTIFICACAO" or proposta["certificacoes"]:
            return None
        return None  # sem dado na proposta: passa adiante, vira UNKNOWN

    def desconhecido(req):
        return Decisao("UNKNOWN", "A proposta não traz informação sobre este requisito.")

    requisitos = [{"categoria": "SLA", "sugerido": False}, {"categoria": "CERTIFICACAO", "sugerido": False},
                  {"categoria": "SLA", "sugerido": True}]
    linhas = []
    for req in requisitos:
        decisao = sourcing.avaliacao.decidir(req, [sla, certificacao], req["sugerido"], desconhecido)
        linhas.append({"status": decisao.status, "status_calculado": decisao.status})
    assert [linha["status"] for linha in linhas] == ["COMPLIANT", "UNKNOWN", "REQUIRES_REVIEW"]
    ajustada = sourcing.avaliacao.ajustar(dict(linhas[1]), "NON_COMPLIANT", {"justificativa": "Sem ISO no anexo."})
    assert (ajustada["status"], ajustada["status_calculado"]) == ("NON_COMPLIANT", "UNKNOWN")
    assert sourcing.avaliacao.contar(linhas)["UNKNOWN"] == 1
    assert sourcing.avaliacao.Direcao.PROPOSTA.value == "PROPOSAL"


def test_regra_com_status_fora_do_vocabulario_e_recusada():
    regra = lambda req: sourcing.avaliacao.Decisao("TALVEZ", "?")  # noqa: E731
    with pytest.raises(ValueError):
        sourcing.avaliacao.decidir({}, [regra], False, lambda r: sourcing.avaliacao.Decisao("UNKNOWN", ""))


def _formula_anterior(icp_cnaes, icp_ufs, icp_porte, cnae, uf, porte) -> float:
    """Cópia da fórmula de `predator.prospeccao._score_aderencia` antes da S1 (sem a penalidade de descarte)."""
    from app.providers.account_data.receita_federal_downloader import normalizar_cnae

    pontuacao = 0.0
    if cnae in {normalizar_cnae(c) for c in icp_cnaes}:
        pontuacao += 0.5
    if uf.upper() in {u.upper() for u in icp_ufs}:
        pontuacao += 0.3
    if icp_porte and porte == icp_porte:
        pontuacao += 0.2
    return round(pontuacao, 2)


def test_estrategia_icp_tem_paridade_com_a_formula_anterior_do_predator():
    icps = [(["6201-5/01"], ["SP"], "grande"), (["6201501", "8610101"], ["sp", "RJ"], None), ([], [], "media")]
    candidatos = itertools.product(["6201501", "8610101", "1111111"], ["SP", "rj", "MG"], ["grande", "media", None])
    for (cnaes, ufs, porte_icp), (cnae, uf, porte) in itertools.product(icps, list(candidatos)):
        novo = matching.combinar(matching.criterios_icp(cnaes, ufs, porte_icp, cnae, uf, porte)).pontuacao
        assert novo == _formula_anterior(cnaes, ufs, porte_icp, cnae, uf, porte), (cnaes, ufs, porte_icp, cnae, uf, porte)


def test_fit_da_rede_passa_a_casar_cnae_pontuado_com_digitos():
    """Correção de bug trazida pela estratégia única: o ICP guarda o CNAE como
    digitado e o fit da rede comparava sem normalizar ("8610-1/01" ≠ "8610101")."""
    resultado = matching.combinar(matching.criterios_icp(["8610-1/01"], ["SP"], "grande", "8610101", None, "grande"))
    assert resultado.pontuacao == 0.7 and resultado.faltantes == ["sede_uf"] and resultado.confianca == "media"


def test_nucleo_nao_importa_modelos_de_nenhum_dos_lados():
    proibidos = ("app.models.", "app.contexts.bids", "app.contexts.procurement")
    for arquivo in (RAIZ / "app" / "contexts" / "sourcing").glob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith(proibidos), f"{arquivo.name} importa {no.module}"
