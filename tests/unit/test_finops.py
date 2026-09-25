"""AI FinOps & Credits (Fase 5): custo, créditos, carteira, orçamentos e o
GATE §82 — nenhuma chamada de IA sem contabilização."""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.finops import creditos, orcamentos, precos
from app.contexts.intelligence.gateway import ContextoIA, gerar, limitador_automatico
from app.contexts.intelligence.registro import FEATURES
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.carteira_creditos import MovimentoCredito
from app.models.registro_uso_ia import RegistroUsoIa
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider

TENANT = "tenant-finops"


class LLMComModelo(FakeLLMProvider):
    def __init__(self, modelo="claude-sonnet-5"):
        super().__init__()
        self.modelo = modelo

    def generate(self, request):
        self.chamadas.append(request)
        return LLMResponse(content="ok", model=self.modelo, input_tokens=1000, output_tokens=500,
                           cache_creation_input_tokens=200, cache_read_input_tokens=10000)


@pytest.fixture(autouse=True)
def _precos(db_session):
    precos.garantir_precos_referencia(db_session)
    limitador_automatico.resetar()


def _ativar_politica(db, creditos_por_usd=100.0, **kw):
    return creditos.definir_politica(db, None, creditos_por_usd, kw.get("permite_excedente", False), kw.get("exige_saldo", False), None)


def _chamar(db, llm, feature="crm.meeting_brief", tenant=TENANT):
    return gerar(db, llm, ContextoIA(tenant_id=tenant, feature=feature), LLMRequest(prompt="p"))


def test_custo_por_chamada_com_os_quatro_tipos_de_token(db_session):
    preco = precos.obter_preco(db_session, "claude-sonnet-5")
    # (1000×2 + 500×10 + 200×2,5 + 10000×0,2) / 1e6
    assert precos.calcular_custo(preco, 1000, 500, 200, 10000) == Decimal("0.00950000")


def test_preco_por_maior_prefixo_e_modelo_desconhecido_sem_custo(db_session):
    assert precos.obter_preco(db_session, "claude-sonnet-5-20260801").modelo == "claude-sonnet-5"
    assert precos.obter_preco(db_session, "claude-opus-5-5").modelo == "claude-opus-5-5"
    assert precos.obter_preco(db_session, "modelo-desconhecido") is None


def test_semente_da_migracao_bate_com_a_referencia_do_codigo():
    caminho = next(Path("alembic/versions").glob("*_finops_creditos_ia.py"))
    spec = importlib.util.spec_from_file_location("mig_finops", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert modulo._PRECOS == precos.PRECOS_REFERENCIA


def test_politica_pendente_mede_custo_mas_nao_debita(db_session):
    assert creditos.politica_vigente(db_session) is None or creditos.politica_vigente(db_session).status != "ATIVA"
    _chamar(db_session, LLMComModelo())
    linha = db_session.query(RegistroUsoIa).one()
    assert Decimal(str(linha.custo_usd)) == Decimal("0.0095") and linha.creditos_consumidos is None
    assert db_session.query(MovimentoCredito).count() == 0


def test_politica_ativa_debita_a_carteira_atomicamente_com_o_ledger(db_session):
    _ativar_politica(db_session, 100.0)
    creditos.alocar(db_session, TENANT, 10, None, "teste")
    _chamar(db_session, LLMComModelo())

    linha = db_session.query(RegistroUsoIa).one()
    assert Decimal(str(linha.creditos_consumidos)) == Decimal("0.9500")
    consumo = db_session.query(MovimentoCredito).filter_by(tipo="CONSUMO").one()
    assert consumo.registro_uso_ia_id == linha.id and Decimal(str(consumo.quantidade)) == Decimal("-0.95")
    assert creditos.saldo(db_session, TENANT) == Decimal("9.05")


def test_exige_saldo_bloqueia_antes_do_provedor(db_session):
    _ativar_politica(db_session, 100.0, exige_saldo=True)
    llm = LLMComModelo()
    with pytest.raises(RegraNegocioViolada):
        _chamar(db_session, llm)
    assert llm.chamadas == []
    assert db_session.query(RegistroUsoIa).one().status == "bloqueado"


def test_excedente_permitido_deixa_saldo_negativo_e_registra_excedente(db_session):
    _ativar_politica(db_session, 100.0, exige_saldo=True, permite_excedente=True)
    _chamar(db_session, LLMComModelo())
    assert db_session.query(MovimentoCredito).one().tipo == "EXCEDENTE"
    assert creditos.saldo(db_session, TENANT) < 0


def test_orcamento_bloquear_por_feature_nao_afeta_outra_feature(db_session):
    orcamentos.criar(db_session, TENANT, {"escopo": "feature", "alvo": "crm.meeting_brief", "limite_chamadas": 2, "acao": "BLOQUEAR"})
    llm = LLMComModelo()
    _chamar(db_session, llm)
    _chamar(db_session, llm)
    with pytest.raises(RegraNegocioViolada):
        _chamar(db_session, llm)
    _chamar(db_session, llm, feature="intelligence.estrategia_venda")
    assert len(llm.chamadas) == 3


def test_orcamento_alertar_nao_bloqueia_mas_sinaliza(db_session):
    orcamentos.criar(db_session, TENANT, {"escopo": "tenant", "limite_chamadas": 1, "acao": "ALERTAR"})
    llm = LLMComModelo()
    _chamar(db_session, llm)
    _chamar(db_session, llm)
    estado = orcamentos.estados(db_session, TENANT)[0]
    assert estado.estourado and estado.em_alerta and len(llm.chamadas) == 2


def test_orcamento_de_um_tenant_nao_bloqueia_outro(db_session):
    orcamentos.criar(db_session, TENANT, {"escopo": "tenant", "limite_chamadas": 1, "acao": "BLOQUEAR"})
    llm = LLMComModelo()
    _chamar(db_session, llm)
    _chamar(db_session, llm, tenant="outro-tenant-finops")
    assert len(llm.chamadas) == 2


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_gate_nenhuma_chamada_de_ia_sem_contabilizacao(db_session, feature):
    """GATE da Fase 5 (§82): toda feature registrada, ao passar pelo
    gateway, gera ledger com custo, créditos e movimento na carteira."""
    _ativar_politica(db_session, 100.0)
    creditos.alocar(db_session, TENANT, 1000, None, "gate")
    llm = LLMComModelo()
    _chamar(db_session, llm, feature=feature)

    linhas = db_session.query(RegistroUsoIa).all()
    assert len(linhas) == len(llm.chamadas) == 1
    linha = linhas[0]
    assert linha.feature == feature and linha.status == "sucesso"
    assert linha.custo_usd is not None and linha.creditos_consumidos is not None
    assert db_session.query(MovimentoCredito).filter_by(registro_uso_ia_id=linha.id).count() == 1
