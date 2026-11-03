"""Descoberta paga por busca de mapa: estima antes, exige o custo confirmado, cria contas com sinais e não duplica o que já existe."""

import pytest

from app.contexts.predator import descoberta, sinais
from app.models.conta import Conta
from app.providers.descoberta_empresas.base import DescobertaEmpresasProvider, DescobertaIndisponivel, EmpresaDescoberta
from app.providers.descoberta_empresas.desativado import DescobertaDesativadaProvider
from app.services.errors import RegraNegocioViolada, ValidacaoFalhou

TENANT = "tenant-descoberta"


class FonteFalsa(DescobertaEmpresasProvider):
    custo_por_busca_usd = 0.002

    def __init__(self, resultados: dict[str, list[EmpresaDescoberta]] | None = None, falhar_em: set[str] = frozenset()):
        self.resultados = resultados or {}
        self.falhar_em = falhar_em
        self.chamadas: list[str] = []

    def buscar(self, termo, cidade, limite=20):
        self.chamadas.append(f"{termo} {cidade}")
        if cidade in self.falhar_em:
            raise DescobertaIndisponivel("sem saldo")
        return self.resultados.get(cidade, [])


def _achada(nome, site=None, posicao=1, nota=4.6, avaliacoes=120, busca="contabilidade Campinas"):
    return EmpresaDescoberta(nome=nome, site=site, telefone="(19) 3333-4444", posicao=posicao, nota=nota, avaliacoes=avaliacoes, busca=busca)


def test_estimativa_multiplica_termos_por_cidades_e_respeita_o_teto():
    estimativa = descoberta.estimar(FonteFalsa(), ["contabilidade", "escritório contábil"], ["Campinas", "Jundiaí", "Sorocaba"], 20)
    assert (estimativa.buscas, estimativa.custo_usd) == (6, 0.012)
    with pytest.raises(ValidacaoFalhou):
        descoberta.estimar(FonteFalsa(), ["a", "b", "c"], ["x", "y"], 5)


def test_sem_chave_nao_executa_nem_chama(db_session):
    with pytest.raises(RegraNegocioViolada):
        descoberta.executar(db_session, TENANT, "1", DescobertaDesativadaProvider(), ["contabilidade"], ["Campinas"], 0.0, 20)


def test_custo_nao_confirmado_nao_chama_a_fonte(db_session):
    fonte = FonteFalsa()
    with pytest.raises(RegraNegocioViolada):
        descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 0.0, 20)
    assert fonte.chamadas == []


def test_cria_contas_com_sinais_e_trata_rede_social_como_sem_site(db_session):
    fonte = FonteFalsa({"Campinas": [
        _achada("Contábil Alfa", site="https://www.alfacontabil.com.br/", posicao=2),
        _achada("Escritório Beta", site="https://instagram.com/beta", posicao=7, nota=3.9),
    ]})

    resultado = descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 0.002, 20)

    assert resultado == {"buscas": 1, "criadas": 2, "atualizadas": 0, "enfileiradas": 1, "falhas": []}  # só a que tem site vai para a fila
    alfa = db_session.query(Conta).filter_by(tenant_id=TENANT, nome="Contábil Alfa").one()
    beta = db_session.query(Conta).filter_by(tenant_id=TENANT, nome="Escritório Beta").one()
    assert alfa.dominio == "alfacontabil.com.br" and alfa.origem == "descoberta_busca" and alfa.regiao == "Campinas"
    assert beta.dominio is None
    vigentes = sinais.vigentes(db_session, TENANT, [alfa.id, beta.id])
    assert vigentes[alfa.id]["POSICAO_MAPA"].valor_num == 2 and vigentes[alfa.id]["SEM_SITE"].valor_num == 0
    assert vigentes[beta.id]["SEM_SITE"].valor_num == 1 and vigentes[beta.id]["NOTA_AVALIACOES"].valor_num == 3.9


def test_empresa_que_ja_existe_so_ganha_sinais(db_session):
    db_session.add(Conta(tenant_id=TENANT, nome="Alfa Contabilidade Ltda", dominio="alfacontabil.com.br", status="priorizada"))
    db_session.commit()
    fonte = FonteFalsa({"Campinas": [_achada("Contábil Alfa", site="alfacontabil.com.br", posicao=4)]})

    resultado = descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 0.002, 20)

    assert resultado["criadas"] == 0 and resultado["atualizadas"] == 1
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT).one()
    assert conta.status == "priorizada"
    assert sinais.vigentes(db_session, TENANT, [conta.id])[conta.id]["POSICAO_MAPA"].valor_num == 4


def test_falha_numa_busca_nao_derruba_as_outras(db_session):
    fonte = FonteFalsa({"Jundiaí": [_achada("Gama Contábil", site="gama.com.br")]}, falhar_em={"Campinas"})

    resultado = descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas", "Jundiaí"], 0.004, 20)

    assert resultado["buscas"] == 1 and resultado["criadas"] == 1 and len(resultado["falhas"]) == 1


def test_coorte_por_posicao_no_mapa(db_session):
    from app.services import conta_service

    fonte = FonteFalsa({"Campinas": [_achada("Topo", site="topo.com.br", posicao=1), _achada("Meio", site="meio.com.br", posicao=12)]})
    descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 0.002, 20)

    resultado = conta_service.coorte_por_sinais(db_session, TENANT, None, False, [{"codigo": "POSICAO_MAPA", "regra": "faixa", "minimo": 4}])

    assert [c["nome"] for c in resultado["contas"]] == ["Meio"]
