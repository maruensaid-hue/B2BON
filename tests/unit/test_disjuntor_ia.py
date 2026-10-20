"""Disjuntor do gateway de IA: provedor fora do ar falha rápido, sem cobrar e sem martelar; recupera sozinho."""

import pytest

from app.contexts.intelligence.disjuntor import Disjuntor, disjuntor_ia
from app.contexts.intelligence.gateway import ContextoIA, gerar
from app.core.config import settings
from app.llm.base import LLMFalhaDeProvedor, LLMIndisponivel
from app.contexts.finops import carteira
from app.llm.schemas import LLMRequest
from app.models.creditos_ia import ExecucaoIa
from app.models.registro_uso_ia import RegistroUsoIa
from app.services.errors import IAIndisponivel
from tests.fakes import FakeLLMProvider

TENANT = "tenant-disjuntor"
CTX = ContextoIA(tenant_id=TENANT, feature="plataforma.faq")


class _Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


class _Fora(FakeLLMProvider):
    def __init__(self, erro: Exception) -> None:
        super().__init__(["x"])
        self.erro, self.chamadas_feitas = erro, 0

    def generate(self, request):
        self.chamadas_feitas += 1
        raise self.erro


@pytest.fixture(autouse=True)
def _limiares(monkeypatch):
    monkeypatch.setattr(settings, "ai_disjuntor_falhas", 3)
    monkeypatch.setattr(settings, "ai_disjuntor_pausa_segundos", 60)


def test_abre_apos_n_falhas_seguidas_e_fecha_com_sucesso():
    relogio = _Relogio()
    d = Disjuntor(relogio)
    for _ in range(2):
        d.falha()
    assert d.permite() and not d.aberto()
    d.falha()
    assert d.aberto() and not d.permite()


def test_sucesso_zera_a_contagem():
    d = Disjuntor(_Relogio())
    d.falha()
    d.falha()
    d.sucesso()
    d.falha()
    d.falha()
    assert d.permite()


def test_meio_aberto_libera_uma_chamada_de_teste_e_reabre_se_falhar():
    relogio = _Relogio()
    d = Disjuntor(relogio)
    for _ in range(3):
        d.falha()
    relogio.agora += 61
    assert d.permite() is True          # a chamada de teste
    assert d.permite() is False         # as demais esperam o resultado do teste
    d.falha()                           # o teste falhou: pausa inteira de novo
    relogio.agora += 30
    assert d.permite() is False
    relogio.agora += 31
    assert d.permite() is True
    d.sucesso()
    assert d.permite() and not d.aberto()


def test_zero_desliga_o_disjuntor(monkeypatch):
    monkeypatch.setattr(settings, "ai_disjuntor_falhas", 0)
    d = Disjuntor(_Relogio())
    for _ in range(50):
        d.falha()
    assert d.permite()


def test_gateway_abre_o_circuito_e_para_de_chamar_o_provedor(db_session):
    llm = _Fora(LLMFalhaDeProvedor("timeout"))
    for _ in range(3):
        with pytest.raises(IAIndisponivel):
            gerar(db_session, llm, CTX, LLMRequest(prompt="p"))
    assert llm.chamadas_feitas == 3

    with pytest.raises(IAIndisponivel, match="temporariamente indisponível"):
        gerar(db_session, llm, CTX, LLMRequest(prompt="p"))

    assert llm.chamadas_feitas == 3  # a 4ª nem chegou ao provedor
    ultimo = db_session.query(RegistroUsoIa).order_by(RegistroUsoIa.id.desc()).first()
    assert (ultimo.status, ultimo.erro) == ("bloqueado", "disjuntor aberto")


def test_gateway_fecha_o_circuito_quando_o_provedor_volta(db_session, monkeypatch):
    relogio = _Relogio()
    monkeypatch.setattr(disjuntor_ia, "_relogio", relogio)
    ruim = _Fora(LLMFalhaDeProvedor("fora do ar"))
    for _ in range(3):
        with pytest.raises(IAIndisponivel):
            gerar(db_session, ruim, CTX, LLMRequest(prompt="p"))

    relogio.agora += 61
    resposta = gerar(db_session, FakeLLMProvider(["voltei"]), CTX, LLMRequest(prompt="p"))

    assert resposta.content == "voltei"
    assert not disjuntor_ia.aberto()


def test_resposta_vazia_ou_cortada_nao_conta_como_provedor_fora_do_ar(db_session):
    """`LLMIndisponivel` simples (texto vazio, cortado por tokens) significa que o provedor respondeu: não abre o circuito."""
    llm = _Fora(LLMIndisponivel("A IA não retornou texto na resposta."))
    for _ in range(6):
        with pytest.raises(IAIndisponivel):
            gerar(db_session, llm, CTX, LLMRequest(prompt="p"))
    assert llm.chamadas_feitas == 6 and not disjuntor_ia.aberto()


def test_chamada_barrada_pelo_disjuntor_libera_a_reserva_de_creditos(db_session):
    llm = _Fora(LLMFalhaDeProvedor("fora"))
    for _ in range(4):
        with pytest.raises(IAIndisponivel):
            gerar(db_session, llm, CTX, LLMRequest(prompt="p"))
    execucoes = db_session.query(ExecucaoIa).filter_by(tenant_id=TENANT).all()
    assert len(execucoes) == 4 and {e.status for e in execucoes} == {"LIBERADA"}
    assert carteira.reconciliar(db_session, TENANT)["consistente"]
