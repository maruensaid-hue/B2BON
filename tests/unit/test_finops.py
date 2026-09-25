"""AI FinOps & Credits (Fases 5 e 15): custo, créditos pelo peso do workload,
carteira, orçamentos e o GATE — nenhuma chamada de IA sem contabilização."""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.finops import carteira, orcamentos, precos
from app.contexts.finops.comercial import TipoLote
from app.contexts.intelligence.gateway import ContextoIA, gerar, limitador_automatico
from app.contexts.intelligence.registro import FEATURES, WORKLOAD_POR_FEATURE
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import ExecucaoIa
from app.models.registro_uso_ia import RegistroUsoIa
from app.services.errors import CreditosInsuficientes, RegraNegocioViolada
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


def _saldo(db, quantidade):
    carteira.conceder(db, TENANT, TipoLote.ADJUSTMENT, quantidade, "teste")
    db.commit()


def test_custo_medido_e_credito_pelo_peso_do_workload_nao_pelo_custo(db_session, cobranca_ativa):
    """Fase 15: crédito vem do peso do workload (meeting_intelligence = 10),
    o custo do provedor é medido à parte e vira margem."""
    _saldo(db_session, 100)
    _chamar(db_session, LLMComModelo())
    linha = db_session.query(RegistroUsoIa).one()
    assert Decimal(str(linha.custo_usd)) == Decimal("0.0095") and linha.workload_codigo == "meeting_intelligence"
    execucao = db_session.get(ExecucaoIa, linha.execucao_id)
    assert (execucao.status, float(execucao.creditos_liquidados), float(execucao.custo_total_usd)) == ("LIQUIDADA", 10, 0.0095)
    assert float(execucao.economia_cache_usd) > 0  # 10.000 tokens lidos do cache
    db_session.expire_all()
    assert carteira.disponivel(db_session, TENANT) == 90


def test_sem_saldo_bloqueia_antes_do_provedor(db_session, cobranca_ativa):
    llm = LLMComModelo()
    with pytest.raises(CreditosInsuficientes):
        _chamar(db_session, llm)
    assert llm.chamadas == []
    assert db_session.query(RegistroUsoIa).one().status == "bloqueado"


def test_excedente_enterprise_aprovado_vira_consumo_faturavel(db_session, cobranca_ativa):
    config = carteira.configuracao(db_session, TENANT)
    config.excedente_ativo, config.excedente_aprovado_por, config.excedente_limite_rigido = True, "super", 50
    db_session.commit()
    _chamar(db_session, LLMComModelo())
    excedente = db_session.query(MovimentoCredito).filter_by(tipo="CREDIT_OVERAGE").one()
    assert excedente.faturavel and float(excedente.quantidade) == -10
    assert carteira.excedente_no_mes(db_session, TENANT) == 10
    for _ in range(4):
        _chamar(db_session, LLMComModelo())
    with pytest.raises(CreditosInsuficientes):  # limite rígido do excedente (50)
        _chamar(db_session, LLMComModelo())


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
def test_gate_nenhuma_chamada_de_ia_sem_contabilizacao(db_session, feature, cobranca_ativa):
    """GATE §82 (Fase 5) + §63 (Fase 15): toda feature registrada, ao passar
    pelo gateway, gera evento de uso com custo, execução liquidada com o
    peso do workload e consumo no extrato da carteira."""
    _saldo(db_session, 1000)
    llm = LLMComModelo()
    gerar(db_session, llm, ContextoIA(tenant_id=TENANT, feature=feature, confirmado=True), LLMRequest(prompt="p"))

    linhas = db_session.query(RegistroUsoIa).all()
    assert len(linhas) == len(llm.chamadas) == 1
    linha = linhas[0]
    assert linha.feature == feature and linha.status == "sucesso" and linha.custo_usd is not None
    assert linha.workload_codigo == WORKLOAD_POR_FEATURE[feature] and linha.catalogo_versao == "CREDIT_CATALOG_V1"
    execucao = db_session.get(ExecucaoIa, linha.execucao_id)
    assert execucao.status == "LIQUIDADA" and execucao.creditos_liquidados > 0
    assert float(execucao.custo_total_usd) == float(linha.custo_usd)
    assert db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_CONSUMED").count() >= 1
    assert carteira.reconciliar(db_session, TENANT)["consistente"]
