"""API dos AI Credits (Fase 15): pacotes públicos, carteira do tenant,
compra via webhook, recarga com consentimento, orçamento, admin auditado,
catálogos versionados e isolamento entre tenants."""

import hashlib
import hmac

import pytest

from app.contexts.finops import carteira, execucoes
from app.core.config import settings
from app.models.auditoria import AuditLog
from app.models.creditos_ia import CompraCreditos, LoteCreditos

TENANT = "tenant-teste"
PRECOS_PO = {"AI_START": (5000, 99.0), "AI_15K": (15000, 249.0), "AI_30K": (30000, 449.0), "AI_75K": (75000, 899.0),
             "AI_150K": (150000, 1499.0), "AI_350K": (350000, 2999.0), "AI_1M": (1000000, 6990.0), "ENTERPRISE": (None, None)}


@pytest.fixture()
def segredo_mp(monkeypatch):
    monkeypatch.setattr(settings, "mercadopago_webhook_secret", "segredo-creditos")
    return "segredo-creditos"


def _assinatura(payment_id: str, segredo: str) -> dict:
    manifest = f"id:{payment_id.lower()};request-id:req-1;ts:1700000000;"
    v1 = hmac.new(segredo.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts=1700000000,v1={v1}", "x-request-id": "req-1"}


def test_pacotes_publicos_vem_do_catalogo_sem_preco_inventado(client):
    resposta = client.get("/api/v1/ai-credits/pacotes", headers={"Authorization": ""})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert {p["codigo"]: (p["creditos"], p["preco"]) for p in corpo["pacotes"]} == PRECOS_PO
    enterprise = next(p for p in corpo["pacotes"] if p["codigo"] == "ENTERPRISE")
    assert enterprise["status"] == "CONTACT_SALES"
    franquias = {f["produto"]: f for f in corpo["franquias"]}
    assert franquias["procurement"]["creditos"] is None and franquias["procurement"]["status"] == "PENDING_FINAL_DEFINITION"
    assert franquias["full_suite"]["creditos"] is None
    assert corpo["regras"]["franquia_mensal_acumula"] is False and corpo["regras"]["validade_topup_meses"] == 12


def test_carteira_mostra_franquia_do_plano_sem_custo_em_usd(client):
    corpo = client.get("/api/v1/ai-credits/carteira").json()
    assert corpo["franquia_mensal"] == 35_000 and corpo["incluido_no_plano"] == 35_000 and corpo["disponivel"] == 35_000
    assert corpo["uso_do_mes"]["percentual"] == 0
    assert "usd" not in str(corpo).lower()


def test_compra_so_credita_pelo_webhook_e_uma_unica_vez(client, db_session, fake_payment, segredo_mp):
    compra = client.post("/api/v1/ai-credits/compras", json={"pacote": "AI_15K"})
    assert compra.status_code == 201
    compra = compra.json()
    assert (compra["status"], compra["creditos"], compra["preco"]) == ("PENDENTE", 15000, 249.0)
    assert compra["url_checkout"].startswith("https://checkout.stub.local/")
    antes = client.get("/api/v1/ai-credits/carteira").json()["disponivel"]

    pagamento = fake_payment.aprovar(next(iter(fake_payment._preferencias)))
    for _ in range(2):  # webhook repetido (timeout do provedor) não credita em dobro
        assert client.post(f"/api/v1/webhooks/mercadopago?data.id={pagamento}", headers=_assinatura(pagamento, segredo_mp)).status_code == 200

    carteira_depois = client.get("/api/v1/ai-credits/carteira").json()
    assert carteira_depois["disponivel"] - antes == 15000 and carteira_depois["comprado"] == 15000
    lote = db_session.query(LoteCreditos).filter_by(tenant_id=TENANT, tipo="TOPUP").one()
    assert float(lote.receita_por_credito_brl) == pytest.approx(249 / 15000)
    assert (lote.expira_em - lote.concedido_em).days in range(364, 367)  # 12 meses
    assert db_session.query(CompraCreditos).one().status == "APROVADA"
    assert carteira.reconciliar(db_session, TENANT)["consistente"]


def test_webhook_com_valor_divergente_nao_credita(client, db_session, fake_payment, segredo_mp):
    client.post("/api/v1/ai-credits/compras", json={"pacote": "AI_START"})
    preferencia = next(iter(fake_payment._preferencias))
    fake_payment._preferencias[preferencia]["valor"] = 1.0  # adulterado
    pagamento = fake_payment.aprovar(preferencia)
    client.post(f"/api/v1/webhooks/mercadopago?data.id={pagamento}", headers=_assinatura(pagamento, segredo_mp))
    assert db_session.query(CompraCreditos).one().status == "REJEITADA"
    assert db_session.query(LoteCreditos).filter_by(tenant_id=TENANT, tipo="TOPUP").count() == 0


def test_enterprise_e_contact_sales(client):
    assert client.post("/api/v1/ai-credits/compras", json={"pacote": "ENTERPRISE"}).status_code == 422


def test_recarga_automatica_exige_consentimento_e_cria_pedido(client, db_session):
    sem = client.put("/api/v1/ai-credits/recarga-automatica", json={"ativa": True, "limiar": 40_000, "pacote": "AI_START"})
    assert sem.status_code == 422
    com = client.put("/api/v1/ai-credits/recarga-automatica",
                     json={"ativa": True, "limiar": 40_000, "pacote": "AI_START", "consentimento": True}).json()
    assert com["ativa"] and com["consentido_em"]
    execucao = execucoes.abrir(db_session, TENANT, "short_summary")
    execucoes.liquidar(db_session, execucao.id)  # saldo < limiar → pedido pendente (sem cobrança fora de sessão)
    pedidos = client.get("/api/v1/ai-credits/compras").json()
    assert [(p["origem"], p["status"]) for p in pedidos] == [("AUTO_RECARGA", "PENDENTE")]
    execucao = execucoes.abrir(db_session, TENANT, "short_summary")
    execucoes.liquidar(db_session, execucao.id)
    assert len(client.get("/api/v1/ai-credits/compras").json()) == 1  # um pedido por vez


def test_orcamento_por_modulo_bloqueia_com_parada_rigida(client, db_session, cobranca_ativa):
    resposta = client.put("/api/v1/ai-credits/orcamento", json={"limites_modulo_percentual": {"predator": 0.0001}})
    assert resposta.status_code == 200
    from app.services.errors import OrcamentoIaExcedido

    with pytest.raises(OrcamentoIaExcedido):
        execucoes.abrir(db_session, TENANT, "cadence_generation", modulo="predator")
    auditoria = db_session.query(AuditLog).filter_by(tenant_id=TENANT, evento_tipo="orcamento_creditos_ia_definido").one()
    assert auditoria.detalhes["valor_novo"]["limites_modulo_percentual"] == {"predator": 0.0001}
    invalido = client.put("/api/v1/ai-credits/orcamento", json={"limites_modulo_percentual": {"predator": 1.5}})
    assert invalido.status_code == 422


def test_estimativa_e_execucoes_sem_custo(client, db_session):
    estimativa = client.post("/api/v1/ai-credits/estimativas",
                             json={"workload": "procurement_document_intelligence", "parametros": {"paginas": 200}}).json()
    assert estimativa["creditos_estimados"] == 225 and estimativa["requer_confirmacao"] is True
    execucao = execucoes.abrir(db_session, TENANT, "opportunity_intelligence")
    execucoes.liquidar(db_session, execucao.id)
    linhas = client.get("/api/v1/ai-credits/execucoes").json()
    assert linhas[0]["creditos_liquidados"] == 15 and "custo" not in str(linhas).lower()
    consumo = client.get("/api/v1/ai-credits/consumo").json()
    assert consumo["por_workload"][0] == {"chave": "opportunity_intelligence", "execucoes": 1, "creditos": 15}


def test_tenant_nao_ve_carteira_nem_lote_de_outro(client, db_session, criar_usuario_autenticado):
    lote = carteira.conceder(db_session, TENANT, carteira.TipoLote.TOPUP, 777, "teste")
    db_session.commit()
    outro = criar_usuario_autenticado("tenant-outro", papel="admin", email="admin@outro.com")
    assert client.get(f"/api/v1/ai-credits/lotes/{lote.id}", headers=outro).status_code == 404
    corpo = client.get("/api/v1/ai-credits/carteira", headers=outro).json()
    assert corpo["comprado"] == 0 and all(item["id"] != lote.id for item in corpo["lotes"])
    assert all(m["lote_id"] != lote.id for m in client.get("/api/v1/ai-credits/extrato", headers=outro).json())


def test_usuario_comum_nao_compra_nem_ve_extrato(client, criar_usuario_autenticado):
    vendedor = criar_usuario_autenticado(TENANT, papel="vendedor", email="vendedor@t.com")
    assert client.post("/api/v1/ai-credits/compras", json={"pacote": "AI_START"}, headers=vendedor).status_code == 403
    assert client.get("/api/v1/ai-credits/extrato", headers=vendedor).status_code == 403
    assert client.get("/api/v1/ai-credits/carteira", headers=vendedor).status_code == 200


def test_admin_da_plataforma_e_so_super_admin(client, criar_usuario_autenticado):
    admin = criar_usuario_autenticado(TENANT, papel="admin", email="admin@t.com")
    for rota in ("/api/v1/finops/economia", "/api/v1/finops/margens", "/api/v1/finops/catalogo", "/api/v1/finops/reconciliacao",
                 "/api/v1/finops/matriz-rentabilidade", "/api/v1/finops/relatorio-calibracao"):
        assert client.get(rota, headers=admin).status_code == 403, rota
    assert client.post(f"/api/v1/finops/tenants/{TENANT}/creditos", json={"quantidade": 10, "motivo": "auto-bônus"},
                       headers=admin).status_code == 403


def test_catalogo_versionado_rascunho_e_ativacao_auditados(client, db_session):
    rascunho = client.post("/api/v1/finops/catalogo/rascunhos",
                           json={"mudancas": {"cadence_generation": {"creditos_base": 10}}, "motivo": "calibração 30d"})
    assert rascunho.status_code == 201
    versao = rascunho.json()["versao"]
    catalogo = client.get("/api/v1/finops/catalogo").json()
    assert catalogo["ativo"] == "CREDIT_CATALOG_V1"  # rascunho não muda nada sozinho
    assert client.post(f"/api/v1/finops/catalogo/{versao}/ativar", json={"motivo": "aprovado pelo PO"}).status_code == 200
    ativo = client.get("/api/v1/finops/catalogo").json()
    assert ativo["ativo"] == versao
    assert next(w for w in ativo["workloads"] if w["codigo"] == "cadence_generation")["creditos_base"] == 10
    assert db_session.query(AuditLog).filter(AuditLog.evento_tipo.like("catalogo_credito%")).count() >= 2


def test_nova_versao_de_pacote_preserva_historico(client):
    resposta = client.post("/api/v1/finops/pacotes/AI_START/versoes",
                           json={"preco": 109, "creditos": 5000, "validade_meses": 12, "motivo": "reajuste aprovado"})
    assert resposta.status_code == 201 and resposta.json()["versao"] == 2
    historico = [p for p in client.get("/api/v1/finops/pacotes").json() if p["codigo"] == "AI_START"]
    assert [(p["versao"], p["preco"]) for p in historico] == [(1, 99.0), (2, 109.0)]
    publicos = {p["codigo"]: p["preco"] for p in client.get("/api/v1/ai-credits/pacotes").json()["pacotes"]}
    assert publicos["AI_START"] == 109.0


def test_economia_e_reconciliacao_para_super_admin(client, db_session):
    execucao = execucoes.abrir(db_session, TENANT, "tender_analysis")
    execucoes.liquidar(db_session, execucao.id)
    kpis = client.get("/api/v1/finops/economia?dias=30").json()
    assert kpis["credits_consumed"] == 50 and kpis["ai_revenue_brl"] == pytest.approx(50 * 6.99 / 1000, abs=0.01)
    assert kpis["ai_gross_margin"] is None and kpis["motivo_indisponivel"]  # sem câmbio configurado: margem UNKNOWN, não inventada
    assert client.get("/api/v1/finops/margens?dimensao=workload").status_code == 200
    assert client.get("/api/v1/finops/margens?dimensao=inexistente").status_code == 422
    assert client.get("/api/v1/finops/relatorio-calibracao?dias=7").status_code == 200
    assert all(r["consistente"] for r in client.get("/api/v1/finops/reconciliacao").json())


def test_estorno_admin_devolve_creditos(client, db_session):
    execucao = execucoes.abrir(db_session, TENANT, "tender_analysis")
    execucoes.liquidar(db_session, execucao.id)
    antes = client.get("/api/v1/ai-credits/carteira").json()["disponivel"]
    resposta = client.post(f"/api/v1/finops/execucoes/{execucao.id}/estorno", json={"motivo": "falha do provedor"})
    assert resposta.json()["status"] == "ESTORNADA"
    assert client.get("/api/v1/ai-credits/carteira").json()["disponivel"] - antes == 50


def test_excedente_enterprise_configurado_pelo_super_admin(client, db_session, cobranca_ativa):
    resposta = client.put(f"/api/v1/finops/tenants/{TENANT}/excedente",
                          json={"ativo": True, "limite_rigido": 1000, "franquia_personalizada": 100, "motivo": "contrato Enterprise"})
    assert resposta.status_code == 200
    assert client.get("/api/v1/ai-credits/carteira").json()["franquia_mensal"] == 100


def test_rotina_horaria_e_idempotente(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "cron-teste")
    for _ in range(2):
        resposta = client.post("/api/v1/cron/creditos-ia", headers={"X-Cron-Secret": "cron-teste"})
        assert resposta.status_code == 200 and resposta.json()["falhas"] == 0
    assert db_session.query(LoteCreditos).filter_by(tenant_id=TENANT, tipo="SUBSCRIPTION").count() == 1
