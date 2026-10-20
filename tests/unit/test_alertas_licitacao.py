"""Correspondência determinística dos alertas de licitação: compatível, incompatível, dados ausentes, pontuação explicável."""

from datetime import datetime, timedelta

import pytest

from app.contexts.bids import alertas
from app.models.licitacao_publica import LicitacaoPublica

AGORA = datetime(2026, 10, 20, 12, 0)


def _pub(**kw) -> LicitacaoPublica:
    base = dict(fonte="PNCP", fonte_id_externo="1", titulo="Aquisição de licenças de software de gestão", objeto="Contratação de solução de TI",
                orgao_nome="Prefeitura de Campinas", uf="SP", modalidade="PUBLIC_TENDER", valor_estimado=500000.0,
                prazo_proposta=AGORA + timedelta(days=20), situacao_externa="Divulgada")
    base.update(kw)
    return LicitacaoPublica(**base)


def _regra(**kw) -> dict:
    base = dict(nome="R", palavras_chave=["software"], palavras_excluir=[], ufs=[], modalidades=[], valor_minimo=None, valor_maximo=None,
                dias_minimos_prazo=None, usar_portfolio=False, relevancia_minima=40, icp_id=None)
    base.update(kw)
    return base


def test_edital_compativel_pontua_e_explica_cada_fator():
    c = alertas.avaliar_item(_regra(ufs=["SP"], valor_minimo=100000, valor_maximo=900000, modalidades=["PUBLIC_TENDER"], dias_minimos_prazo=10), _pub(), AGORA)

    # 1 palavra casada = 40 de 60; UF 20/20 + valor 10/10 + modalidade 5/5 + prazo 5/5  =>  80 de 100
    assert c is not None and c.score == 80
    fatores = {f["fator"]: f for f in c.fatores}
    assert set(fatores) == {"palavras_chave", "uf", "valor", "modalidade", "prazo"}
    assert "software" in fatores["palavras_chave"]["detalhe"] and "SP" in fatores["uf"]["detalhe"] and "20 dias" in fatores["prazo"]["detalhe"]
    assert sum(f["pontos"] for f in c.fatores) <= sum(f["maximo"] for f in c.fatores)


@pytest.mark.parametrize("regra", [
    dict(palavras_chave=["hospital"]),                       # nenhuma palavra no objeto
    dict(palavras_excluir=["gestao"]),                        # palavra excluída presente (sem acento na regra, com acento no edital)
    dict(ufs=["RJ"]),                                         # outra UF
    dict(valor_minimo=1_000_000),                             # abaixo da faixa
    dict(valor_maximo=100_000),                               # acima da faixa
    dict(modalidades=["DIRECT_AWARD"]),                       # outra modalidade
    dict(dias_minimos_prazo=30),                              # prazo curto demais
])
def test_edital_incompativel_nao_gera_correspondencia(regra):
    assert alertas.avaliar_item(_regra(**regra), _pub(), AGORA) is None


def test_palavra_e_busca_sem_acento_com_plural_mas_sem_casar_no_meio_de_outra_palavra():
    assert alertas.avaliar_item(_regra(palavras_chave=["licença"]), _pub(), AGORA) is not None      # 'licença' casa 'licenças'
    assert alertas.avaliar_item(_regra(palavras_chave=["GESTÃO"]), _pub(), AGORA) is not None        # maiúscula/acento irrelevantes
    assert alertas.avaliar_item(_regra(palavras_chave=["ti"]), _pub(titulo="Gestão de pessoal", objeto="Pessoal", orgao_nome="X"), AGORA) is None
    assert alertas.avaliar_item(_regra(palavras_chave=["ti"]), _pub(), AGORA) is not None            # 'TI' como palavra


def test_dado_ausente_na_fonte_nao_exclui_mas_nao_pontua_e_diz_isso():
    c = alertas.avaliar_item(_regra(ufs=["SP"], valor_minimo=1, relevancia_minima=0), _pub(uf=None, valor_estimado=None), AGORA)

    assert c is not None
    por_fator = {f["fator"]: f for f in c.fatores}
    assert por_fator["uf"]["pontos"] == 0 and "não informou" in por_fator["uf"]["detalhe"]
    assert por_fator["valor"]["pontos"] == 0 and "não informado" in por_fator["valor"]["detalhe"]
    assert c.score < 100  # incerteza reduz a compatibilidade


def test_relevancia_minima_corta_correspondencia_fraca():
    regra = _regra(ufs=["SP"], valor_minimo=1, relevancia_minima=90)
    assert alertas.avaliar_item(regra, _pub(uf=None, valor_estimado=None), AGORA) is None
    assert alertas.avaliar_item({**regra, "relevancia_minima": 10}, _pub(uf=None, valor_estimado=None), AGORA) is not None


def test_mais_palavras_casadas_dao_mais_pontos():
    uma = alertas.avaliar_item(_regra(palavras_chave=["software", "hospital"]), _pub(), AGORA)
    tres = alertas.avaliar_item(_regra(palavras_chave=["software", "licencas", "gestao"]), _pub(), AGORA)
    assert tres.fatores[0]["pontos"] > uma.fatores[0]["pontos"]


def test_edital_com_prazo_vencido_nunca_gera_correspondencia():
    assert alertas.avaliar_item(_regra(), _pub(prazo_proposta=AGORA - timedelta(days=1)), AGORA) is None
    assert alertas.avaliar_item(_regra(), _pub(prazo_proposta=None), AGORA) is not None  # sem prazo informado: segue


def test_regra_vinculada_a_icp_herda_as_ufs_do_icp_quando_nao_tem_as_proprias():
    regra = _regra(icp_id=7)
    assert alertas.avaliar_item(regra, _pub(uf="SP"), AGORA, ufs_do_icp=["SP", "MG"]) is not None
    assert alertas.avaliar_item(regra, _pub(uf="BA"), AGORA, ufs_do_icp=["SP", "MG"]) is None
    assert alertas.avaliar_item({**regra, "ufs": ["BA"]}, _pub(uf="BA"), AGORA, ufs_do_icp=["SP"]) is not None  # a própria UF da regra prevalece


def test_portfolio_acrescenta_palavras_do_nome_da_oferta():
    regra = _regra(palavras_chave=[], usar_portfolio=True)
    c = alertas.avaliar_item(regra, _pub(), AGORA, tokens_portfolio=["software", "cibernetica"])

    assert c is not None and "do portfólio" in c.fatores[0]["detalhe"]
    assert alertas.avaliar_item(regra, _pub(), AGORA, tokens_portfolio=["cibernetica"]) is None
    assert alertas.avaliar_item(regra, _pub(), AGORA, tokens_portfolio=[]) is None  # sem oferta ativa: nada a casar, e nunca "tudo"
