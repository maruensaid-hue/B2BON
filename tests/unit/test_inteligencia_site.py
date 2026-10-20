"""Confirmação de domínio por evidências e extração determinística de indicadores financeiros (sem IA, sem rede)."""

import pytest

from app.contexts.predator.inteligencia_site import derivar_indicadores, extrair_indicadores, verificar_dominio

CNPJ = "33000167000101"
REGISTRO = {
    "razao_social": "PETROLEO BRASILEIRO S A PETROBRAS", "nome_fantasia": "PETROBRAS", "email": "contato@petrobras.com.br",
    "cep": "20031170", "logradouro": "REPUBLICA DO CHILE", "numero": "65", "ddd_telefone_1": "2121660000",
}


def _v(paginas, cnpj=CNPJ, registro=REGISTRO, dominio="petrobras.com.br", nome="Petrobras"):
    return verificar_dominio(dominio, paginas, cnpj, nome, registro)


def _tipos(v):
    return {e["tipo"] for e in v.evidencias if e["encontrada"]}


# --- Domínio ------------------------------------------------------------------------------------------------------------


def test_cnpj_da_conta_exibido_no_site_confirma():
    v = _v([("https://petrobras.com.br/", "Rodapé: CNPJ 33.000.167/0001-01 - Av. qualquer")])
    assert v.situacao == "confirmado" and "cnpj_exato" in _tipos(v) and not v.exige_validacao_manual


def test_cnpj_sem_pontuacao_tambem_vale():
    assert _v([("u", f"cnpj {CNPJ}")]).situacao == "confirmado"


def test_filial_com_a_mesma_raiz_confirma_com_registro_da_evidencia():
    v = _v([("u", "Filial CNPJ 33.000.167/0007-31")])
    assert v.situacao == "confirmado" and "cnpj_mesma_raiz" in _tipos(v)


def test_email_do_cadastro_no_mesmo_dominio_mais_endereco_confirma_sem_cnpj_no_site():
    v = _v([("u", "Nossa sede: Republica do Chile, 65 - Centro, Rio de Janeiro")])
    assert v.situacao == "confirmado" and _tipos(v) == {"email_dominio", "endereco"}
    assert any("não exibe CNPJ" in l for l in v.limitacoes)


def test_so_email_e_cep_fica_provavel_e_pede_validacao_manual():
    v = _v([("u", "CEP 20031-170")])
    assert v.situacao == "provavel" and v.exige_validacao_manual and v.pontuacao == 55


def test_nome_parecido_sozinho_nunca_confirma():
    v = _v([("u", "Petrobras Distribuidora de Alimentos Ltda")], registro={**REGISTRO, "email": None})
    assert v.situacao == "inconclusivo" and _tipos(v) == {"nome"}
    assert any("não informa e-mail" in l for l in v.limitacoes)


def test_site_com_outro_cnpj_e_sem_prova_e_divergente():
    v = _v([("u", "Empresa XYZ - CNPJ 11.222.333/0001-81")], dominio="xyz.com.br", registro={**REGISTRO, "email": None})
    assert v.situacao == "divergente" and any(e["tipo"] == "cnpj_divergente" for e in v.evidencias)


def test_outro_cnpj_mas_com_email_e_endereco_do_cadastro_nao_e_divergente():
    # grupo/parceiro exibindo outro CNPJ no rodapé, mas com e-mail e endereço oficiais batendo
    v = _v([("u", "Parceiro CNPJ 11.222.333/0001-81. Sede Republica do Chile, 65")])
    assert v.situacao == "confirmado"


def test_sem_cnpj_e_sem_registro_registra_as_limitacoes_em_vez_de_inventar():
    v = verificar_dominio("alpha.com.br", [("u", "Alpha Tech soluções")], None, "Alpha Tech", None)
    assert v.situacao == "inconclusivo"
    assert len(v.limitacoes) == 2 and any("CNPJ da conta" in l for l in v.limitacoes) and any("Cadastro público" in l for l in v.limitacoes)


def test_cnpj_da_conta_no_site_confirma_mesmo_sem_consultar_o_cadastro_publico():
    v = verificar_dominio("alpha.com.br", [("u", "CNPJ: 33.000.167/0001-01")], CNPJ, "Alpha", None)
    assert v.situacao == "confirmado"
    assert any("Cadastro público" in l for l in v.limitacoes)


def test_subdominio_do_email_conta_como_mesmo_dominio():
    v = _v([("u", "Republica do Chile, 65")], dominio="www.petrobras.com.br", registro={**REGISTRO, "email": "ri@mail.petrobras.com.br"})
    assert "email_dominio" in _tipos(v)


def test_logradouro_sem_o_numero_proximo_nao_conta_como_endereco():
    v = _v([("u", "Republica do Chile fica no centro. Telefone fixo na página de contato, número 9999")])
    assert "endereco" not in _tipos(v)


def test_telefone_do_cadastro_soma_pontos():
    assert "telefone" in _tipos(_v([("u", "Ligue (21) 2166-0000")]))


# --- Indicadores financeiros -----------------------------------------------------------------------------------------


def test_extrai_valor_escala_moeda_periodo_e_fonte():
    texto = "No 3T25 a receita líquida foi de R$ 12,3 bilhões, alta de 8%."
    [ind] = extrair_indicadores([("https://ri.exemplo.com.br/resultados", texto)])
    assert (ind.nome, ind.valor, ind.moeda, ind.escala, ind.periodo, ind.confianca) == ("receita_liquida", 12.3e9, "BRL", "bilhoes", "2025-T3", "alta")
    assert ind.valor_original == "R$ 12,3 bilhões" and ind.url == "https://ri.exemplo.com.br/resultados"
    assert "receita líquida" in ind.trecho and ind.tipo == "publicado" and ind.metodo == "regex_deterministico_v1"


def test_milhar_com_ponto_e_decimal_com_virgula():
    [ind] = extrair_indicadores([("u", "Exercício de 2024: lucro líquido de R$ 1.234,56 mil.")])
    assert ind.valor == pytest.approx(1_234_560.0) and ind.periodo == "2024"


def test_sem_periodo_no_trecho_a_confianca_e_baixa_e_o_periodo_fica_vazio():
    [ind] = extrair_indicadores([("u", "A receita bruta alcançou R$ 800 milhões.")])
    assert ind.periodo is None and ind.confianca == "baixa" and ind.valor == 800e6


def test_percentual_ou_numero_sem_moeda_nao_vira_indicador():
    assert extrair_indicadores([("u", "A receita líquida cresceu 12% em 2025 e o EBITDA foi forte.")]) == []


def test_pagina_sem_dados_financeiros_nao_inventa_nada():
    assert extrair_indicadores([("u", "Somos uma empresa de tecnologia fundada em 2010.")]) == []


def test_mesmo_valor_repetido_na_pagina_nao_duplica():
    texto = "Receita líquida de R$ 5 milhões em 2025. Repetindo: receita líquida de R$ 5 milhões em 2025."
    assert len(extrair_indicadores([("u", texto)])) == 1


def test_moeda_usd_e_respeitada_sem_conversao():
    [ind] = extrair_indicadores([("u", "EBITDA ajustado de US$ 40 milhões em 2025")])
    assert (ind.nome, ind.moeda, ind.valor) == ("ebitda", "USD", 40e6)


def test_margem_derivada_so_com_mesma_pagina_periodo_e_moeda_com_formula_e_origens():
    publicados = extrair_indicadores([("u", "Em 2025 a receita líquida foi de R$ 200 milhões e o lucro líquido de R$ 20 milhões.")])
    [margem] = derivar_indicadores(publicados)
    assert (margem.nome, margem.valor, margem.tipo, margem.periodo) == ("margem_liquida_pct", 10.0, "derivado", "2025")
    assert margem.formula == "lucro_liquido / receita_liquida × 100" and len(margem.origens) == 2


@pytest.mark.parametrize(
    "paginas",
    [
        [("a", "Em 2025 receita líquida de R$ 200 milhões."), ("b", "Em 2025 lucro líquido de R$ 20 milhões.")],   # páginas diferentes
        [("a", "Em 2025 receita líquida de R$ 200 milhões. Em 2024 lucro líquido de R$ 20 milhões." + " " * 400)],  # períodos diferentes
        [("a", "Em 2025 receita líquida de R$ 200 milhões. Em 2025 lucro líquido de US$ 20 milhões.")],            # moedas diferentes
        [("a", "Receita líquida de R$ 200 milhões e lucro líquido de R$ 20 milhões.")],                             # sem período
    ],
)
def test_nao_deriva_misturando_paginas_periodos_moedas_ou_sem_periodo(paginas):
    assert derivar_indicadores(extrair_indicadores(paginas)) == []
