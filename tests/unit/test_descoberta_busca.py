"""Descoberta por busca de mapa: estima antes, exige as buscas confirmadas, conta a franquia do mês, cria contas com sinais e não duplica."""

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
        descoberta.executar(db_session, TENANT, "1", DescobertaDesativadaProvider(), ["contabilidade"], ["Campinas"], 1, 20)


def test_buscas_nao_confirmadas_nao_chamam_a_fonte(db_session):
    fonte = FonteFalsa()
    with pytest.raises(RegraNegocioViolada):
        descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 2, 20)
    assert fonte.chamadas == []


def test_cria_contas_com_sinais_e_trata_rede_social_como_sem_site(db_session):
    fonte = FonteFalsa({"Campinas": [
        _achada("Contábil Alfa", site="https://www.alfacontabil.com.br/", posicao=2),
        _achada("Escritório Beta", site="https://instagram.com/beta", posicao=7, nota=3.9),
    ]})

    resultado = descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 1, 20)

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

    resultado = descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 1, 20)

    assert resultado["criadas"] == 0 and resultado["atualizadas"] == 1
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT).one()
    assert conta.status == "priorizada"
    assert sinais.vigentes(db_session, TENANT, [conta.id])[conta.id]["POSICAO_MAPA"].valor_num == 4


def test_falha_numa_busca_nao_derruba_as_outras(db_session):
    fonte = FonteFalsa({"Jundiaí": [_achada("Gama Contábil", site="gama.com.br")]}, falhar_em={"Campinas"})

    resultado = descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas", "Jundiaí"], 2, 20)

    assert resultado["buscas"] == 1 and resultado["criadas"] == 1 and len(resultado["falhas"]) == 1


def test_coorte_por_posicao_no_mapa(db_session):
    from app.services import conta_service

    fonte = FonteFalsa({"Campinas": [_achada("Topo", site="topo.com.br", posicao=1), _achada("Meio", site="meio.com.br", posicao=12)]})
    descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas"], 1, 20)

    resultado = conta_service.coorte_por_sinais(db_session, TENANT, None, False, [{"codigo": "POSICAO_MAPA", "regra": "faixa", "minimo": 4}])

    assert [c["nome"] for c in resultado["contas"]] == ["Meio"]


def test_franquia_conta_so_as_buscas_feitas_e_barra_o_que_passa_do_mes(db_session):
    fonte = FonteFalsa({"Jundiaí": [_achada("Gama Contábil", site="gama.com.br")]}, falhar_em={"Campinas"})
    descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas", "Jundiaí"], 2, 20, franquia_mensal=3)

    assert descoberta.usadas_no_mes(db_session, TENANT) == 1  # a busca que falhou não consome a franquia
    estimativa = descoberta.estimar(fonte, ["contabilidade", "advocacia"], ["Sorocaba", "Jundiaí"], 20, db_session, TENANT, 3)
    assert (estimativa.buscas, estimativa.usadas_no_mes, estimativa.franquia_mensal) == (4, 1, 3)
    with pytest.raises(RegraNegocioViolada, match="2 busca"):
        descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade", "advocacia"], ["Sorocaba", "Jundiaí"], 4, 20, franquia_mensal=3)
    assert descoberta.usadas_no_mes(db_session, "outro-tenant") == 0


def test_sem_franquia_definida_conta_o_uso_sem_barrar(db_session):
    fonte = FonteFalsa()
    for _ in range(3):
        descoberta.executar(db_session, TENANT, "1", fonte, ["contabilidade"], ["Campinas", "Jundiaí"], 2, 20)
    assert descoberta.usadas_no_mes(db_session, TENANT) == 6


def test_mes_da_franquia_e_o_de_brasilia():
    from datetime import UTC, datetime

    # 01/12 01:00 UTC ainda é 30/11 22:00 em Brasília: o mês é novembro
    assert descoberta._inicio_do_mes_utc(datetime(2026, 12, 1, 1, 0, tzinfo=UTC)) == datetime(2026, 11, 1, 3, 0)
    assert descoberta._inicio_do_mes_utc(datetime(2026, 12, 1, 4, 0, tzinfo=UTC)) == datetime(2026, 12, 1, 3, 0)


# --- Base aberta de mapas ----------------------------------------------------------------------------------------------------

def _cliente_mapa(lugares, chamadas):
    import httpx

    def responder(pedido: httpx.Request) -> httpx.Response:
        chamadas.append(pedido)
        if "nominatim" in pedido.url.host:
            return httpx.Response(200, json=[{"osm_type": "node", "osm_id": 1}, {"osm_type": "relation", "osm_id": 298255}])
        return httpx.Response(200, json={"elements": lugares})

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_mapa_aberto_converte_lugares_e_reaproveita_a_area_da_cidade(monkeypatch):
    from app.providers.descoberta_empresas import mapa_aberto

    monkeypatch.setattr(mapa_aberto.time, "sleep", lambda _s: None)
    chamadas = []
    lugares = [
        {"tags": {"name": "Contábil Alfa", "office": "accountant", "website": "https://alfa.com.br", "phone": "+55 19 3333-4444",
                  "addr:street": "Rua X", "addr:housenumber": "10", "addr:city": "Campinas"}},
        {"tags": {"name": "Contábil Alfa", "office": "accountant"}},  # repetido (nó e prédio do mesmo lugar)
        {"tags": {"name": "Beta Contabilidade", "shop": "yes", "contact:phone": "1999"}},
        {"tags": {"office": "accountant"}},  # sem nome: ignorado
    ]
    fonte = mapa_aberto.MapaAbertoProvider(_cliente_mapa(lugares, chamadas))

    achadas = fonte.buscar("escritório de contabilidade", "Campinas SP")
    fonte.buscar("advocacia", "Campinas SP")

    assert [a.nome for a in achadas] == ["Contábil Alfa", "Beta Contabilidade"]
    alfa = achadas[0]
    assert (alfa.site, alfa.telefone, alfa.categoria, alfa.posicao, alfa.nota) == ("https://alfa.com.br", "+55 19 3333-4444", "accountant", 1, None)
    assert alfa.endereco == "Rua X 10, Campinas" and achadas[1].telefone == "1999" and achadas[1].categoria is None
    assert sum("nominatim" in c.url.host for c in chamadas) == 1  # cidade localizada uma vez só na execução
    consulta = [c for c in chamadas if "overpass" in c.url.host][0].content.decode()
    assert "3600298255" in consulta and "accountant" in consulta and fonte.custo_por_busca_usd == 0


def test_mapa_aberto_cidade_inexistente_ou_termo_vazio_viram_falha_da_busca(monkeypatch):
    import httpx

    from app.providers.descoberta_empresas import mapa_aberto

    monkeypatch.setattr(mapa_aberto.time, "sleep", lambda _s: None)
    sem_cidade = mapa_aberto.MapaAbertoProvider(httpx.Client(transport=httpx.MockTransport(lambda _p: httpx.Response(200, json=[]))))
    with pytest.raises(DescobertaIndisponivel, match="UF"):
        sem_cidade.buscar("contabilidade", "Cidadezinha")
    with pytest.raises(DescobertaIndisponivel, match="genérico"):
        sem_cidade.buscar("de da", "Campinas SP")


def test_sem_chave_paga_a_fonte_padrao_e_a_base_aberta(monkeypatch):
    from app.api import deps
    from app.core.config import settings
    from app.providers.descoberta_empresas.mapa_aberto import MapaAbertoProvider

    monkeypatch.setattr(settings, "descoberta_busca_api_key", "")
    assert isinstance(deps.get_descoberta_provider(), MapaAbertoProvider)


class _Admin:
    papel = "admin"


def test_fonte_lenta_confere_na_hora_e_roda_em_segundo_plano(db_session, monkeypatch):
    from fastapi import BackgroundTasks

    from app.api.v1 import descoberta as rota
    from app.core.config import settings

    class FonteLenta(FonteFalsa):
        lenta = True

    fonte = FonteLenta({"Campinas": [_achada("Delta Contábil", site="delta.com.br")]})
    tarefas = BackgroundTasks()
    pedido = rota.ExecutarDescobertaSchema(termos=["contabilidade"], cidades=["Campinas"], buscas_confirmadas=1)

    resposta = rota.executar(pedido, tarefas, TENANT, "1", db_session, fonte, lambda: db_session, _Admin())

    assert resposta == {"em_segundo_plano": True, "buscas": 1} and fonte.chamadas == []  # nada buscado antes de responder
    monkeypatch.setattr(db_session, "close", lambda: None)
    for tarefa in tarefas.tasks:
        tarefa.func(*tarefa.args, **tarefa.kwargs)
    assert fonte.chamadas == ["contabilidade Campinas"]
    assert db_session.query(Conta).filter_by(tenant_id=TENANT, nome="Delta Contábil").count() == 1

    monkeypatch.setattr(settings, "descoberta_busca_franquia_mensal", 1)
    with pytest.raises(RegraNegocioViolada, match="franquia"):  # recusa aparece na hora, não some no segundo plano
        rota.executar(pedido, BackgroundTasks(), TENANT, "1", db_session, fonte, lambda: db_session, _Admin())


def test_franquia_segue_a_regua_da_pesquisa_de_decisores(db_session, monkeypatch):
    from types import SimpleNamespace

    from app.api.v1 import descoberta as rota
    from app.contexts.enriquecimento import config as config_enriquecimento
    from app.core.config import settings

    monkeypatch.setattr(settings, "descoberta_busca_franquia_mensal", 0)
    monkeypatch.setattr(settings, "enriquecimento_super_admin_sem_limites", True)
    monkeypatch.setattr(config_enriquecimento, "config_vigente", lambda _db, _t: (SimpleNamespace(franquia_creditos=60), None))
    assert rota.franquia_do_tenant(db_session, TENANT, "admin") == (60, False)  # Professional: 60 por mês
    assert rota.franquia_do_tenant(db_session, TENANT, "super_admin") == (0, False)  # super admin sem limites, como nos decisores

    monkeypatch.setattr(config_enriquecimento, "config_vigente", lambda _db, _t: (None, "poc_sem_autorizacao"))
    assert rota.franquia_do_tenant(db_session, TENANT, "admin") == (3, True)  # POC: 3 na vida da empresa

    monkeypatch.setattr(config_enriquecimento, "config_vigente", lambda _db, _t: (None, "sem_plano_ativo"))
    assert rota.franquia_do_tenant(db_session, TENANT, "admin") == (0, False)  # sem configuração: não bloqueia


def test_franquia_da_poc_conta_a_vida_toda(db_session):
    from datetime import UTC, datetime, timedelta

    from app.models.auditoria import AuditLog

    antigo = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)
    db_session.add(AuditLog(tenant_id=TENANT, evento_tipo="descoberta_busca_executada", entidade_tipo="tenant", entidade_id=0,
                            detalhes={"buscas": 2}, criado_em=antigo))
    db_session.commit()
    assert descoberta.usadas_no_mes(db_session, TENANT) == 0
    assert descoberta.usadas_no_mes(db_session, TENANT, vida_toda=True) == 2
    with pytest.raises(RegraNegocioViolada, match="do seu plano"):
        descoberta.executar(db_session, TENANT, "1", FonteFalsa(), ["a1b2", "c3d4"], ["Campinas"], 2, 20, franquia_mensal=3, franquia_vida_toda=True)
