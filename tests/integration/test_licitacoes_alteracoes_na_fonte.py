"""Edital já ingerido que a fonte alterou: situação (anulada, revogada, suspensa) e retificação ficam registradas, sem mexer no status do vendedor."""

from datetime import datetime

import httpx
import pytest

from app.contexts.bids import licitacoes
from app.contexts.bids.fontes.base import LicitacaoExterna
from app.contexts.bids.fontes.pncp import FontePncp, PaginaPncp, normalizar
from app.core.config import settings
from app.models.auditoria import AuditLog
from app.models.licitacao import Licitacao
from app.services.errors import ValidacaoFalhou

TENANT = "tenant-teste"
REGISTRO = {
    "numeroControlePNCP": "11222333000181-1-000045/2026", "objetoCompra": "Aquisição de licenças", "valorTotalEstimado": 1000.0,
    "dataPublicacaoPncp": "2026-10-01T10:00:00", "dataEncerramentoProposta": "2026-10-30T09:00:00", "modalidadeId": 6, "srp": False,
    "anoCompra": 2026, "sequencialCompra": 45, "orgaoEntidade": {"cnpj": "11222333000181", "razaoSocial": "MUNICIPIO X"},
    "situacaoCompraId": 1, "situacaoCompraNome": "Divulgada no PNCP", "dataAtualizacao": "2026-10-01T10:00:00",
    "dataAtualizacaoGlobal": "2026-10-02T08:30:00",
}


def _ext(**mudancas) -> LicitacaoExterna:
    return normalizar({**REGISTRO, **mudancas})


def _eventos(db, tipo):
    return [(a.entidade_id, a.detalhes) for a in db.query(AuditLog).filter_by(tenant_id=TENANT, evento_tipo=tipo).order_by(AuditLog.id)]


def test_normalizar_traz_situacao_e_data_de_atualizacao_da_fonte():
    ext = _ext()
    assert ext.situacao_externa == "Divulgada no PNCP"
    assert ext.atualizado_externo_em == datetime(2026, 10, 2, 8, 30)  # dataAtualizacaoGlobal tem prioridade
    assert _ext(dataAtualizacaoGlobal=None).atualizado_externo_em == datetime(2026, 10, 1, 10, 0)
    assert _ext(situacaoCompraNome=None).situacao_externa is None


def test_primeira_ingestao_guarda_a_situacao_sem_gerar_evento_de_mudanca(db_session):
    resultado = licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext()])
    lic = db_session.get(Licitacao, resultado["criadas"][0])
    assert (lic.situacao_externa, lic.atualizado_externo_em) == ("Divulgada no PNCP", datetime(2026, 10, 2, 8, 30))
    assert resultado["alteradas"] == [] and not _eventos(db_session, "licitacao_situacao_externa_alterada")


def test_recoletar_sem_mudanca_nao_gera_evento_nem_ruido(db_session):
    licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext()])
    for _ in range(3):
        resultado = licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext()])
        assert resultado["alteradas"] == []
    assert not _eventos(db_session, "licitacao_situacao_externa_alterada") and not _eventos(db_session, "licitacao_retificada_na_fonte")
    assert db_session.query(Licitacao).count() == 1


@pytest.mark.parametrize("situacao", ["Anulada", "Revogada", "Suspensa"])
def test_anulacao_revogacao_e_suspensao_ficam_registradas_sinalizadas_e_preservam_o_status_do_vendedor(db_session, situacao):
    criada = licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext()])["criadas"][0]
    lic = db_session.get(Licitacao, criada)
    lic.status = "em_analise"  # o vendedor já trabalhou nesta licitação
    db_session.commit()

    resultado = licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext(situacaoCompraNome=situacao, dataAtualizacaoGlobal="2026-10-10T09:00:00")])

    assert resultado["alteradas"] == [{"id": criada, "situacao_alterada": True, "retificada": False}]
    db_session.refresh(lic)
    assert lic.status == "em_analise" and lic.situacao_externa == situacao  # status interno intacto; situação da fonte atualizada
    [(entidade, detalhes)] = _eventos(db_session, "licitacao_situacao_externa_alterada")
    assert entidade == criada and (detalhes["de"], detalhes["para"], detalhes["exige_atencao"]) == ("Divulgada no PNCP", situacao, True)
    assert detalhes["atualizado_na_fonte_em"] == "2026-10-10T09:00:00"
    assert licitacoes.como_dict(lic)["externa_exige_atencao"] is True


def test_divulgada_nao_exige_atencao(db_session):
    lic = db_session.get(Licitacao, licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext()])["criadas"][0])
    assert licitacoes.como_dict(lic)["externa_exige_atencao"] is False
    assert licitacoes.como_dict(lic)["situacao_externa"] == "Divulgada no PNCP"


def test_retificacao_de_prazo_e_valor_registra_antes_e_depois(db_session):
    criada = licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext()])["criadas"][0]

    resultado = licitacoes.ingerir_detalhado(
        db_session, TENANT, None, [_ext(dataEncerramentoProposta="2026-11-15T09:00:00", valorTotalEstimado=1500.0, dataAtualizacaoGlobal="2026-10-12T10:00:00")]
    )

    assert resultado["alteradas"] == [{"id": criada, "situacao_alterada": False, "retificada": True}]
    [(_, detalhes)] = _eventos(db_session, "licitacao_retificada_na_fonte")
    assert detalhes["campos"] == ["prazo_proposta", "valor_estimado"]
    assert detalhes["prazo_proposta"] == {"de": "2026-10-30T09:00:00", "para": "2026-11-15T09:00:00"}
    assert detalhes["valor_estimado"] == {"de": 1000.0, "para": 1500.0}
    assert db_session.get(Licitacao, criada).valor_estimado == 1500.0


def test_fonte_que_nao_informa_situacao_nao_apaga_a_que_ja_se_conhece(db_session):
    criada = licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext(situacaoCompraNome="Suspensa")])["criadas"][0]
    licitacoes.ingerir_detalhado(db_session, TENANT, None, [_ext(situacaoCompraNome=None, dataAtualizacaoGlobal=None, dataAtualizacao=None)])
    lic = db_session.get(Licitacao, criada)
    assert lic.situacao_externa == "Suspensa" and not _eventos(db_session, "licitacao_situacao_externa_alterada")


def test_ingerir_mantem_o_formato_original_da_resposta(db_session):
    assert set(licitacoes.ingerir(db_session, TENANT, None, [_ext()])) == {"criadas", "atualizadas"}


def test_edital_manual_nao_tem_situacao_externa(db_session):
    lic = licitacoes.criar(db_session, TENANT, None, {"titulo": "Manual", "modalidade": "PUBLIC_TENDER"})
    assert (lic.situacao_externa, licitacoes.como_dict(lic)["externa_exige_atencao"]) == (None, False)


# --- Adapter: endpoint de atualização ----------------------------------------------------------------------------------------------


def _fonte_que_registra():
    caminhos = []

    def responder(request):
        caminhos.append(request.url.path)
        return httpx.Response(200, json={"data": [REGISTRO], "totalRegistros": 1, "totalPaginas": 1, "numeroPagina": 1, "empty": False})

    return FontePncp(httpx.Client(base_url="https://pncp.test/api/consulta/v1", transport=httpx.MockTransport(responder))), caminhos


def test_endpoint_de_atualizacao_e_o_de_publicacao_sao_selecionaveis():
    fonte, caminhos = _fonte_que_registra()
    fonte.buscar_pagina("20261019", "20261020", 6)
    fonte.buscar_pagina("20261019", "20261020", 6, endpoint="atualizacao")
    assert caminhos == ["/api/consulta/v1/contratacoes/publicacao", "/api/consulta/v1/contratacoes/atualizacao"]


def test_endpoint_invalido_e_recusado_sem_chegar_a_rede():
    fonte, caminhos = _fonte_que_registra()
    with pytest.raises(ValidacaoFalhou):
        fonte.buscar_pagina("20261019", "20261020", 6, endpoint="../admin")
    assert caminhos == []


# --- Coleta agendada: usa a atualização e conta as alterações ------------------------------------------------------------------------


def test_coleta_agendada_consulta_a_atualizacao_e_conta_o_que_a_fonte_alterou(db_session, monkeypatch):
    from app.contexts.bids import coleta
    from tests.integration.test_coleta_pncp import AGORA

    class FonteComAlteracao:
        def __init__(self):
            self.endpoints, self.rodada = [], 0

        def buscar_pagina(self, di, df, modalidade, pagina=1, uf=None, endpoint="publicacao"):
            self.endpoints.append(endpoint)
            situacao = "Divulgada no PNCP" if self.rodada == 0 else "Anulada"
            return PaginaPncp([_ext(situacaoCompraNome=situacao)], pagina, 1, 1, 0, 1)

    monkeypatch.setattr(settings, "pncp_habilitado", True)
    coleta.salvar_configuracao(db_session, TENANT, None, {"ativa": True, "modalidades": [6], "palavras_chave": ["licenças"]})
    fonte = FonteComAlteracao()
    primeira = coleta.executar(db_session, TENANT, fonte, agora=AGORA, dormir=lambda s: None)
    fonte.rodada = 1
    segunda = coleta.executar(db_session, TENANT, fonte, agora=AGORA.replace(hour=18), dormir=lambda s: None)

    assert set(fonte.endpoints) == {"atualizacao"}
    assert (primeira.inseridos, primeira.alterados_na_fonte) == (1, 0)
    assert (segunda.inseridos, segunda.atualizados, segunda.alterados_na_fonte) == (0, 1, 1)
    assert coleta.execucao_dict(segunda)["alterados_na_fonte"] == 1
