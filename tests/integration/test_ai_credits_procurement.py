"""Teste crítico §64 (Fase 15) — Public Procurement × AI Credits.

1. Atualização determinística de contrato: 0 AI Credits.
2. Documento de 200 páginas: estimativa → confirmação → reserva →
   liquidação → CREDIT_CONSUMED → uso registrado → margem calculada.
3. O preço base do Public Procurement segue PENDING_DEFINITION.
"""

import pytest

from app.contexts.finops import carteira
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import ExecucaoIa
from app.models.registro_uso_ia import RegistroUsoIa

P = "/api/v1/procurement"
TENANT = "tenant-teste"
pytestmark = pytest.mark.usefixtures("cobranca_ativa")


def _post(client, recurso, corpo):
    resposta = client.post(f"{P}/{recurso}", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_atualizacao_deterministica_de_contrato_nao_consome_creditos(client, db_session):
    antes = client.get("/api/v1/ai-credits/carteira").json()["disponivel"]
    orgao = _post(client, "orgaos", {"nome": "Prefeitura", "cnpj": "11222333000181", "esfera": "municipal"})
    fornecedor = _post(client, "fornecedores", {"razao_social": "Fornecedor X", "cnpj": "11444777000161"})
    contrato = _post(client, "contratos", {"orgao_id": orgao["id"], "fornecedor_id": fornecedor["id"], "numero": "12/2026",
                                           "objeto": "Notebooks", "valor_inicial": 1000})
    assert client.patch(f"{P}/contratos/{contrato['id']}", json={"objeto": "Notebooks e monitores"}).status_code == 200
    assert client.get("/api/v1/ai-credits/carteira").json()["disponivel"] == antes
    assert db_session.query(ExecucaoIa).count() == 0 and db_session.query(RegistroUsoIa).count() == 0


def test_documento_de_200_paginas_estima_confirma_reserva_e_liquida_225(client, db_session, fake_llm):
    texto = "\f".join(f"Página {i}: cláusula de garantia e prazo de entrega." for i in range(1, 201))
    doc = client.post(f"{P}/documentos", data={"tipo": "CONTRATO"}, files={"arquivo": ("c.txt", texto.encode(), "text/plain")}).json()

    estimativa = client.get(f"{P}/documentos/{doc['id']}/estimativa").json()
    assert (estimativa["creditos_estimados"], estimativa["requer_confirmacao"]) == (225, True)
    assert estimativa["mensagem"] == "Consumo estimado: aproximadamente 225 AI Credits."

    antes = client.get("/api/v1/ai-credits/carteira").json()["disponivel"]
    sem_confirmar = client.post(f"{P}/documentos/{doc['id']}/analisar")
    assert sem_confirmar.status_code == 409 and sem_confirmar.json()["requer_confirmacao"] is True
    assert fake_llm.chamadas == [] and client.get("/api/v1/ai-credits/carteira").json()["disponivel"] == antes

    fake_llm.definir_respostas(["[]"] * 500)
    assert client.post(f"{P}/documentos/{doc['id']}/analisar?confirmar=true").status_code == 200

    execucao = db_session.query(ExecucaoIa).filter_by(tenant_id=TENANT).one()
    assert (execucao.workload_codigo, execucao.status) == ("procurement_document_intelligence", "LIQUIDADA")
    assert float(execucao.creditos_estimados) == float(execucao.creditos_liquidados) == 225
    consumo = db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_CONSUMED").all()
    assert sum(-float(m.quantidade) for m in consumo) == 225
    assert db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_RESERVED").count() == 1
    usos = db_session.query(RegistroUsoIa).filter_by(execucao_id=execucao.id).all()
    assert usos and len(usos) == len(fake_llm.chamadas)  # N chamadas, uma cobrança
    assert execucao.custo_llm_usd is not None and float(execucao.receita_brl) > 0
    assert antes - client.get("/api/v1/ai-credits/carteira").json()["disponivel"] == 225
    assert carteira.reconciliar(db_session, TENANT)["consistente"]


def test_preco_do_public_procurement_segue_pendente(client):
    from app.contexts.finops import comercial

    franquia = comercial.FRANQUIAS["procurement"]
    assert franquia.creditos is None and franquia.status == "PENDING_FINAL_DEFINITION"
    catalogo = client.get("/api/v1/catalogo", headers={"Authorization": ""}).json()
    produto = next(p for p in catalogo["produtos"] if p["id"] == "public_procurement")
    assert produto["status_preco"] == "PENDING_DEFINITION" and produto["disponibilidade"] == "EM_DEFINICAO"
    assert all(v is None for v in produto["precificacao_pendente"].values())
    creditos = next(p for p in catalogo["produtos"] if p["id"] == "ai_credits")
    assert next(f for f in creditos["franquias"] if f["produto"] == "procurement")["creditos"] is None
