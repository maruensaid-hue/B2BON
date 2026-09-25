"""AI Gateway × AI Credits (Fase 15): cache, cost guard, falha do
provedor, cobrança de API e coerência feature → workload."""

import pytest

from app.contexts.finops import carteira, catalogos, precos
from app.contexts.finops.comercial import TipoLote
from app.contexts.intelligence import gateway
from app.contexts.intelligence.gateway import ContextoIA, gerar, limitador_automatico
from app.contexts.intelligence.registro import FEATURES, FEATURES_CACHEAVEIS, WORKLOAD_POR_FEATURE, Gatilho
from app.core.config import settings
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import ExecucaoIa
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.tenant import Tenant
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider

TENANT, OUTRO = "tenant-gw-a", "tenant-gw-b"
pytestmark = pytest.mark.usefixtures("cobranca_ativa")


class LLMContado(FakeLLMProvider):
    def generate(self, request):
        self.chamadas.append(request)
        return LLMResponse(content=f"resposta-{len(self.chamadas)}", model=request.model or "claude-sonnet-5",
                           input_tokens=2000, output_tokens=500)


class LLMForaDoAr(FakeLLMProvider):
    def generate(self, request):
        self.chamadas.append(request)
        raise ConnectionError("provedor indisponível")


@pytest.fixture(autouse=True)
def _base(db_session):
    precos.garantir_precos_referencia(db_session)
    limitador_automatico.resetar()
    for tenant in (TENANT, OUTRO):
        db_session.add(Tenant(id=tenant, razao_social=tenant))
        carteira.conceder(db_session, tenant, TipoLote.TOPUP, 1000, "teste")
    db_session.commit()


def _disponivel(db, tenant=TENANT):
    db.expire_all()
    return float(carteira.disponivel(db, tenant))


def test_toda_feature_tem_workload_ativo_no_catalogo(db_session):
    assert set(WORKLOAD_POR_FEATURE) == set(FEATURES)
    codigos = {w.codigo for w in catalogos.workloads(db_session) if w.ativo}
    assert set(WORKLOAD_POR_FEATURE.values()) <= codigos


def test_cache_hit_cobra_credito_mede_economia_e_nao_chama_provedor(db_session):
    llm = LLMContado()
    ctx = ContextoIA(tenant_id=TENANT, feature="plataforma.faq")
    primeira = gerar(db_session, llm, ctx, LLMRequest(prompt="Como funciona o FEFO?"))
    segunda = gerar(db_session, llm, ctx, LLMRequest(prompt="Como funciona o FEFO?"))
    assert "plataforma.faq" in FEATURES_CACHEAVEIS
    assert len(llm.chamadas) == 1 and segunda.content == primeira.content
    hit = db_session.query(RegistroUsoIa).filter_by(tenant_id=TENANT, cache_hit=True).one()
    assert float(hit.custo_usd) == 0 and hit.economia_cache_usd > 0
    assert _disponivel(db_session) == 1000 - 2 * 1  # short_summary = 1 crédito, cobrado nas duas
    execucao = db_session.get(ExecucaoIa, hit.execucao_id)
    assert execucao.cache_hits == 1 and execucao.economia_cache_usd > 0


def test_cache_nao_vaza_entre_tenants(db_session):
    llm = LLMContado()
    gerar(db_session, llm, ContextoIA(tenant_id=TENANT, feature="plataforma.faq"), LLMRequest(prompt="mesma pergunta"))
    gerar(db_session, llm, ContextoIA(tenant_id=OUTRO, feature="plataforma.faq"), LLMRequest(prompt="mesma pergunta"))
    assert len(llm.chamadas) == 2
    assert db_session.query(RegistroUsoIa).filter_by(cache_hit=True).count() == 0


def test_feature_nao_cacheavel_sempre_chama_provedor(db_session):
    llm = LLMContado()
    for _ in range(2):
        gerar(db_session, llm, ContextoIA(tenant_id=TENANT, feature="crm.meeting_brief"), LLMRequest(prompt="igual"))
    assert len(llm.chamadas) == 2


def test_falha_do_provedor_libera_reserva_e_nao_cobra(db_session):
    with pytest.raises(Exception):
        gerar(db_session, LLMForaDoAr(), ContextoIA(tenant_id=TENANT, feature="crm.meeting_brief"), LLMRequest(prompt="p"))
    assert _disponivel(db_session) == 1000
    execucao = db_session.query(ExecucaoIa).filter_by(tenant_id=TENANT).one()
    assert execucao.status == "LIBERADA"
    assert db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_CONSUMED").count() == 0
    assert db_session.query(RegistroUsoIa).filter_by(tenant_id=TENANT).one().status == "falha"
    assert carteira.reconciliar(db_session, TENANT)["consistente"]


def test_chamada_via_api_consome_creditos_e_e_rastreavel(db_session):
    gerar(db_session, LLMContado(), ContextoIA(tenant_id=TENANT, feature="crm.meeting_brief", gatilho=Gatilho.API),
          LLMRequest(prompt="p"))
    execucao = db_session.query(ExecucaoIa).filter_by(tenant_id=TENANT).one()
    assert (execucao.gatilho, execucao.status, float(execucao.creditos_liquidados)) == ("api", "LIQUIDADA", 10)
    assert db_session.query(RegistroUsoIa).filter_by(tenant_id=TENANT).one().gatilho == "api"


def test_limite_de_api_bloqueia_antes_do_provedor(db_session):
    config = carteira.configuracao(db_session, TENANT)
    config.limite_api_creditos = 5
    db_session.commit()
    llm = LLMContado()
    with pytest.raises(RegraNegocioViolada):
        gerar(db_session, llm, ContextoIA(tenant_id=TENANT, feature="crm.meeting_brief", gatilho=Gatilho.API), LLMRequest(prompt="p"))
    assert llm.chamadas == [] and _disponivel(db_session) == 1000


def test_cost_guard_rebaixa_so_ate_a_classe_minima(db_session, monkeypatch):
    monkeypatch.setattr(settings, "ai_modelo_c2", "claude-opus-5")
    monkeypatch.setattr(settings, "ai_modelo_c1", "claude-haiku-4-5")
    requisicao = LLMRequest(prompt="x" * 40_000, max_tokens=4000)
    caro = gateway._estimar_custo_usd(db_session, "claude-opus-5", requisicao)
    barato = gateway._estimar_custo_usd(db_session, "claude-haiku-4-5", requisicao)
    assert barato < caro
    workload = catalogos.obter_workload(db_session, "meeting_intelligence")
    workload.custo_max_usd = (caro + barato) / 2
    db_session.commit()

    llm = LLMContado()
    gerar(db_session, llm, ContextoIA(tenant_id=TENANT, feature="crm.meeting_brief"), requisicao)
    assert llm.chamadas[-1].model == "claude-opus-5"  # classe mínima C2: não rebaixa, só registra
    assert db_session.query(RegistroUsoIa).order_by(RegistroUsoIa.id.desc()).first().decisao_roteamento.startswith(
        "cost_guard:acima_do_teto")

    workload.politica_modelo = {"classe_minima": "C1"}
    db_session.commit()
    gerar(db_session, llm, ContextoIA(tenant_id=TENANT, feature="crm.meeting_brief"), requisicao)
    assert llm.chamadas[-1].model == "claude-haiku-4-5"
    assert db_session.query(RegistroUsoIa).order_by(RegistroUsoIa.id.desc()).first().decisao_roteamento == "cost_guard:C2->C1"
    assert _disponivel(db_session) == 1000 - 2 * 10  # o crédito não muda com o modelo escolhido
