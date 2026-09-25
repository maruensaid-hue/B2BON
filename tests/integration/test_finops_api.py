"""API de FinOps (Fase 5): dashboard da plataforma, visão do tenant sem
custo em USD, política de créditos e alocação."""

from app.contexts.finops import precos
from app.contexts.intelligence.gateway import ContextoIA, gerar
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.auditoria import AuditLog
from tests.fakes import FakeLLMProvider

TENANT = "tenant-teste"


class LLMSonnet(FakeLLMProvider):
    def generate(self, request):
        self.chamadas.append(request)
        return LLMResponse(content="ok", model="claude-sonnet-5", input_tokens=100, output_tokens=50)


def _uso(db, tenant=TENANT, feature="crm.meeting_brief"):
    precos.garantir_precos_referencia(db)
    gerar(db, LLMSonnet(), ContextoIA(tenant_id=tenant, feature=feature), LLMRequest(prompt="p"))


def test_dashboard_da_plataforma_agrega_por_tenant_modulo_e_modelo(client, db_session):
    _uso(db_session)
    _uso(db_session, tenant="outro-tenant")
    resumo = client.get("/api/v1/finops/resumo").json()
    assert resumo["totais"]["chamadas"] == 2 and resumo["totais"]["custo_usd"] > 0
    assert {t["chave"] for t in resumo["por_tenant"]} == {TENANT, "outro-tenant"}
    assert resumo["por_modelo"][0]["chave"] == "claude-sonnet-5"
    assert resumo["receita_ia"] > 0  # Fase 15: créditos da franquia × receita de referência
    assert resumo["margem_bruta_ia"] is None and "FINOPS_CAMBIO_USD_BRL" in resumo["indisponivel"]["margem_bruta_ia"]
    assert resumo["unitarios"]["custo_por_bid_usd"] is None


def test_dashboard_da_plataforma_e_so_super_admin(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT, papel="admin", email="admin-finops@t.com")
    assert client.get("/api/v1/finops/resumo", headers=headers).status_code == 403


def test_tenant_ve_consumo_e_creditos_mas_nao_custo_em_usd(client, db_session, criar_usuario_autenticado):
    _uso(db_session)
    _uso(db_session, tenant="outro-tenant")
    headers = criar_usuario_autenticado(TENANT, papel="admin", email="admin-uso@t.com")
    uso = client.get("/api/v1/finops/meu-uso", headers=headers).json()
    assert uso["chamadas"] == 1
    assert "custo_usd" not in str(uso) and "outro-tenant" not in str(uso)
    assert uso["politica_creditos"] == "PENDING_DEFINITION" or uso["politica_creditos"] is None


def test_tenant_nao_define_orcamento_em_usd_mas_define_por_chamadas(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT, papel="admin", email="admin-orc@t.com")
    assert client.post("/api/v1/finops/orcamentos", json={"limite_custo_usd": 10}, headers=headers).status_code == 403
    assert client.post("/api/v1/finops/orcamentos", json={"limite_chamadas": 100, "acao": "BLOQUEAR"}, headers=headers).status_code == 201
    estados = client.get("/api/v1/finops/orcamentos", headers=headers).json()
    assert estados[0]["limite_chamadas"] == 100 and estados[0]["custo_usd"] is None


def test_super_admin_ajusta_creditos_com_motivo_e_auditoria(client, db_session):
    """Fase 15: a conversão custo→créditos saiu; ajuste administrativo é lote
    auditado (valor anterior e novo)."""
    assert client.post("/api/v1/finops/politica-creditos", json={"creditos_por_usd": 250}).status_code == 405
    sem_motivo = client.post(f"/api/v1/finops/tenants/{TENANT}/creditos", json={"quantidade": 500})
    assert sem_motivo.status_code == 422
    ajuste = client.post(f"/api/v1/finops/tenants/{TENANT}/creditos", json={"quantidade": 500, "motivo": "bônus de lançamento",
                                                                             "tipo": "PROMOTIONAL", "validade_dias": 30}).json()
    assert ajuste["disponivel"] - ajuste["disponivel_anterior"] == 500
    extrato = client.get("/api/v1/ai-credits/extrato").json()
    assert extrato[0]["tipo"] == "CREDIT_PROMOTIONAL" and extrato[0]["quantidade"] == 500
    auditoria = db_session.query(AuditLog).filter_by(tenant_id=TENANT, evento_tipo="creditos_ia_ajustados").one()
    assert auditoria.detalhes["valor_novo"] - auditoria.detalhes["valor_anterior"] == 500 and auditoria.ator_id == "1"


def test_precos_listam_fonte(client, db_session):
    precos.garantir_precos_referencia(db_session)
    linhas = client.get("/api/v1/finops/precos").json()
    assert {"claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"} <= {l["modelo"] for l in linhas}
    assert all(l["fonte"] for l in linhas)
