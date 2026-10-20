"""Os campos de situação externa (V5.2) sobrevivem à ida e volta pelo espelho unificado: sem isso a leitura nova quebrava com AttributeError."""

from datetime import datetime
from app.contexts.bids import espelho
from app.models.licitacao import Licitacao


def _licitacao(**extra):
    base = dict(
        tenant_id="t", modalidade="Pregão", titulo="Edital", objeto="obj", orgao_nome="Órgão", orgao_cnpj=None, conta_id=None, oferta_id=None,
        status="nova", data_publicacao=None, prazo_proposta=None, prazo_esclarecimento=None, valor_estimado=None, responsavel_usuario_id=None,
        fonte="PNCP", fonte_id_externo="1", fonte_url=None, concorrentes=None, parceiros=None, vencedor=None, valor_proposta=None,
        motivo_resultado=None, criado_em=datetime(2026, 10, 1), situacao_externa=None, atualizado_externo_em=None,
    )
    base.update(extra)
    return Licitacao(**base)


def _ida_e_volta(lic):
    linha = {**espelho.processo(lic), "origem_id": 7}
    return espelho.licitacao_de(linha)


def test_situacao_externa_e_data_de_atualizacao_voltam_iguais():
    lic = _licitacao(situacao_externa="Suspensa", atualizado_externo_em=datetime(2026, 10, 18, 9, 30))

    volta = _ida_e_volta(lic)

    assert volta.situacao_externa == "Suspensa"
    assert volta.atualizado_externo_em == datetime(2026, 10, 18, 9, 30)


def test_sem_situacao_externa_volta_nulo_e_registros_antigos_sem_a_chave_nao_quebram():
    assert _ida_e_volta(_licitacao()).situacao_externa is None
    linha = {**espelho.processo(_licitacao()), "origem_id": 1}
    linha["metadados"].pop("situacao_externa")
    linha["metadados"].pop("atualizado_externo_em")
    antigo = espelho.licitacao_de(linha)
    assert antigo.situacao_externa is None and antigo.atualizado_externo_em is None
