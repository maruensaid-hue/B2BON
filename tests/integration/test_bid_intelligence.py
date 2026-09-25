"""Bid Intelligence — Sell Side (Fase 9).

GATE: proveniência de documento validada. Todo requisito gravado aponta
para um documento com hash e fonte, com o trecho literal e a página
calculada pelo sistema; o que a IA não consegue ancorar no texto é
descartado. Também: matriz de conformidade, Go/No-Go humano, cofre,
prazos, concorrência, contratos, ingestão idempotente e isolamento.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fpdf import FPDF

from app.api.deps import get_plan_limits_provider
from app.api.v1.bids import get_fonte_pncp
from app.contexts.bids import analise
from app.contexts.bids.fontes.pncp import FontePncp, normalizar
from app.core.config import settings
from app.main import app
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.requisito_licitacao import RequisitoLicitacao
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT = "tenant-teste"
B = "/api/v1/bids"
PAGINA_1 = "EDITAL DE PREGÃO ELETRÔNICO 12/2026\n1. OBJETO: contratação de solução de gestão de licenças de software."
PAGINA_2 = (
    "5.2 HABILITAÇÃO: apresentar Certidão Negativa de Débitos Federais válida.\n"
    "6.1 A solução deve ter integração com Active Directory.\n"
    "7.1 O prazo de implantação é de 30 dias."
)


def _pdf(*paginas: str) -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for texto in paginas:
        pdf.add_page()
        pdf.multi_cell(0, 8, texto)
    return bytes(pdf.output())


def _licitacao(client, **extra) -> dict:
    corpo = {"titulo": "Pregão 12/2026 — licenças", "orgao_nome": "Prefeitura X", "orgao_cnpj": "11222333000181",
             "prazo_proposta": (datetime.now(UTC) + timedelta(days=20)).isoformat(), **extra}
    resposta = client.post(f"{B}/licitacoes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _enviar(client, licitacao_id, conteudo, tipo="EDITAL", mime="application/pdf", nome="edital.pdf", headers=None):
    return client.post(
        f"{B}/licitacoes/{licitacao_id}/documentos", data={"tipo": tipo},
        files={"arquivo": (nome, conteudo, mime)}, headers=headers or {},
    )


def _itens_ia(*itens) -> str:
    return json.dumps(list(itens), ensure_ascii=False)


# --- GATE: proveniência -------------------------------------------------------


def test_documento_guarda_hash_fonte_e_texto_por_pagina(client, db_session):
    lic = _licitacao(client)
    conteudo = _pdf(PAGINA_1, PAGINA_2)

    doc = _enviar(client, lic["id"], conteudo).json()

    assert doc["sha256"] == hashlib.sha256(conteudo).hexdigest()
    assert doc["paginas"] == 2 and doc["fonte"] == "UPLOAD" and doc["status_analise"] == "PENDENTE"
    salvo = db_session.get(DocumentoLicitacao, doc["id"])
    assert "Certidão Negativa" in salvo.paginas_texto[1]
    baixado = client.get(f"{B}/documentos/{doc['id']}/arquivo")
    assert baixado.content == conteudo and baixado.headers["x-content-sha256"] == doc["sha256"]
    assert _enviar(client, lic["id"], conteudo).status_code == 409  # mesmo arquivo, mesma licitação
    assert _enviar(client, lic["id"], b"nao e pdf").status_code == 422
    assert _enviar(client, lic["id"], b"", mime="text/plain").status_code == 422


def test_analise_so_grava_requisito_ancorado_no_texto_com_pagina_e_clausula_calculadas(client, db_session, fake_llm):
    lic = _licitacao(client)
    doc = _enviar(client, lic["id"], _pdf(PAGINA_1, PAGINA_2)).json()
    fake_llm.definir_respostas([_itens_ia(
        {"categoria": "HABILITACAO", "descricao": "Certidão negativa de débitos federais",
         "citacao": "apresentar Certidão Negativa de Débitos Federais válida", "clausula": "5.2", "pagina": 1},
        {"categoria": "REQUISITO_TECNICO", "descricao": "Integração com Active Directory",
         "citacao": "A solução deve ter integração com Active Directory", "clausula": "9.9"},
        {"categoria": "GARANTIA", "descricao": "Garantia de 5 anos", "citacao": "garantia mínima de cinco anos"},
        {"categoria": "INVENTADA", "descricao": "x", "citacao": "O prazo de implantação é de 30 dias"},
    )])

    resultado = client.post(f"{B}/documentos/{doc['id']}/analisar")

    assert resultado.status_code == 200, resultado.text
    assert resultado.json()["sugeridos"] == 2 and resultado.json()["descartados_sem_evidencia"] == 1
    requisitos = db_session.query(RequisitoLicitacao).filter_by(licitacao_id=lic["id"]).order_by(RequisitoLicitacao.id).all()
    habilitacao, tecnico = requisitos
    assert (habilitacao.documento_id, habilitacao.pagina, habilitacao.clausula) == (doc["id"], 2, "5.2")  # página do texto, não da IA
    assert tecnico.clausula is None  # "9.9" não está na página
    assert all(r.status == "sugerido" and r.origem == "ia" for r in requisitos)
    chamada = fake_llm.chamadas[0]
    assert "<dados_externos" in chamada.prompt and "[[página 2]]" in chamada.prompt
    uso = db_session.query(RegistroUsoIa).filter_by(feature="bids.analise_edital").one()
    assert uso.classe_modelo == "C3" and uso.agente == "tender_analyzer" and uso.entidade_id == doc["id"]


def test_gate_todo_requisito_aponta_para_documento_pagina_e_trecho_literais(client, db_session, fake_llm):
    lic = _licitacao(client)
    edital = _enviar(client, lic["id"], _pdf(PAGINA_1, PAGINA_2)).json()
    tr = _enviar(client, lic["id"], "TR\n4.1 Suporte 24x7 com SLA de 4 horas.\fANEXO\n4.2 Relatórios mensais de uso.".encode(),
                 tipo="TR", mime="text/plain", nome="tr.txt").json()
    fake_llm.definir_respostas([
        _itens_ia({"categoria": "OBJETO", "descricao": "Gestão de licenças", "citacao": "solução de gestão de licenças de software"},
                  {"categoria": "PRAZO", "descricao": "Implantação em 30 dias", "citacao": "O prazo de implantação é de 30 dias"}),
        _itens_ia({"categoria": "SLA", "descricao": "SLA de 4 horas", "citacao": "Suporte 24x7 com SLA de 4 horas", "clausula": "4.1"},
                  {"categoria": "OBRIGACAO", "descricao": "Relatórios mensais", "citacao": "Relatórios mensais de uso"}),
    ])
    client.post(f"{B}/documentos/{edital['id']}/analisar")
    client.post(f"{B}/documentos/{tr['id']}/analisar")
    assert db_session.query(RegistroUsoIa).filter_by(feature="bids.analise_tr").count() == 1

    requisitos = client.get(f"{B}/licitacoes/{lic['id']}/requisitos").json()
    assert len(requisitos) == 4
    documentos = {d.id: d for d in db_session.query(DocumentoLicitacao).filter_by(licitacao_id=lic["id"])}
    for r in requisitos:
        documento = documentos[r["documento_id"]]
        assert documento.sha256 and documento.fonte
        from app.contexts.shared.texto import contem_literal

        assert contem_literal(documento.paginas_texto[r["pagina"] - 1], r["evidencia"]), r
    assert {(r["descricao"], r["pagina"]) for r in requisitos} >= {("Implantação em 30 dias", 2), ("Relatórios mensais", 2)}

    matriz = client.get(f"{B}/licitacoes/{lic['id']}/matriz").json()
    evidencia = next(l for l in matriz["linhas"] if l["categoria"] == "SLA")["evidencia_edital"]
    assert evidencia == {"documento_id": tr["id"], "documento": "tr.txt", "sha256": tr["sha256"], "fonte": "UPLOAD",
                         "fonte_url": None, "pagina": 1, "clausula": "4.1", "trecho": "Suporte 24x7 com SLA de 4 horas"}


def test_documento_longo_e_analisado_em_blocos_e_declara_analise_parcial(client, fake_llm, monkeypatch):
    monkeypatch.setattr(analise, "CARACTERES_POR_BLOCO", 60)
    monkeypatch.setattr(analise, "MAXIMO_BLOCOS", 2)
    lic = _licitacao(client)
    paginas = "\f".join(f"Página {i} com o requisito número {i} do termo." for i in range(1, 6))
    doc = _enviar(client, lic["id"], paginas.encode(), tipo="TR", mime="text/plain", nome="longo.txt").json()
    fake_llm.definir_respostas(["[]", "[]"])

    resultado = client.post(f"{B}/documentos/{doc['id']}/analisar").json()

    assert resultado["blocos_analisados"] == 2 and resultado["analise_parcial"] is True
    assert resultado["paginas_analisadas"] < resultado["paginas_total"] == 5
    assert len(fake_llm.chamadas) == 2


def test_documento_sem_texto_nao_e_analisado_as_cegas(client, fake_llm):
    lic = _licitacao(client)
    doc = _enviar(client, lic["id"], b"   \f  ", mime="text/plain", nome="scan.txt").json()
    assert doc["status_analise"] == "SEM_TEXTO"
    assert client.post(f"{B}/documentos/{doc['id']}/analisar").status_code == 409
    assert fake_llm.chamadas == []


def test_requisito_manual_com_documento_exige_trecho_que_existe(client):
    lic = _licitacao(client)
    doc = _enviar(client, lic["id"], _pdf(PAGINA_1, PAGINA_2)).json()
    base = {"categoria": "PRAZO", "descricao": "Implantação em 30 dias", "documento_id": doc["id"]}
    assert client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json=base).status_code == 422
    assert client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json={**base, "evidencia": "prazo de 90 dias"}).status_code == 422
    criado = client.post(f"{B}/licitacoes/{lic['id']}/requisitos",
                         json={**base, "evidencia": "O prazo de implantação é de 30 dias", "pagina": 1}).json()
    assert criado["pagina"] == 2 and criado["status"] == "confirmado"


# --- Matriz de conformidade e Go/No-Go ----------------------------------------


def _requisito(client, lic_id, categoria, descricao):
    return client.post(f"{B}/licitacoes/{lic_id}/requisitos", json={"categoria": categoria, "descricao": descricao}).json()


def _cofre(client, nome, valido_ate, tipo="CERTIDAO"):
    return client.post(f"{B}/cofre", data={"tipo": tipo, "nome": nome, "valido_ate": valido_ate.isoformat()},
                       files={"arquivo": ("c.pdf", b"%PDF-1.4 certidao", "application/pdf")}).json()


def test_matriz_cruza_requisitos_com_cofre_oferta_e_perfil(client, criar_oferta, fake_llm):
    oferta = criar_oferta(requisitos=["Integração com Active Directory"])
    lic = _licitacao(client, oferta_id=oferta["id"])
    prazo = datetime.now(UTC).date() + timedelta(days=20)
    cofre_ok = _cofre(client, "Certidão Negativa de Débitos Federais", prazo + timedelta(days=60))
    assert cofre_ok["sha256"] == hashlib.sha256(b"%PDF-1.4 certidao").hexdigest()
    _cofre(client, "Certidão de Regularidade do FGTS", prazo - timedelta(days=5))
    reqs = {
        "cnd": _requisito(client, lic["id"], "HABILITACAO", "Certidão negativa de débitos federais"),
        "fgts": _requisito(client, lic["id"], "HABILITACAO", "Certidão de regularidade do FGTS"),
        "ad": _requisito(client, lic["id"], "REQUISITO_TECNICO", "Integração com Active Directory"),
        "iso": _requisito(client, lic["id"], "CERTIFICACAO", "Certificação ISO 27001"),
        "ad_doc": _requisito(client, lic["id"], "QUALIFICACAO_TECNICA", "Atestado de integração com Active Directory"),
    }
    doc = _enviar(client, lic["id"], _pdf(PAGINA_1, PAGINA_2)).json()
    fake_llm.definir_respostas([_itens_ia({"categoria": "SLA", "descricao": "Implantação", "citacao": "O prazo de implantação é de 30 dias"})])
    client.post(f"{B}/documentos/{doc['id']}/analisar")

    linhas = {l["requisito_id"]: l for l in client.get(f"{B}/licitacoes/{lic['id']}/matriz").json()["linhas"]}

    assert linhas[reqs["cnd"]["id"]]["status"] == "COMPLIANT"
    assert linhas[reqs["cnd"]["id"]]["evidencia"][0]["id"] == cofre_ok["id"]
    assert linhas[reqs["fgts"]["id"]]["status"] == "NON_COMPLIANT" and "Renovar" in linhas[reqs["fgts"]["id"]]["risco"]
    assert linhas[reqs["ad"]["id"]]["status"] == "COMPLIANT" and linhas[reqs["ad"]["id"]]["fonte"] == "offer_intelligence"
    assert linhas[reqs["ad_doc"]["id"]]["status"] == "PARTIALLY_COMPLIANT"
    assert linhas[reqs["iso"]["id"]]["status"] == "UNKNOWN"
    sugerido = next(l for l in linhas.values() if l["categoria"] == "SLA")
    assert sugerido["status"] == "REQUIRES_REVIEW"

    ajuste = f"{B}/requisitos/{reqs['iso']['id']}/conformidade"
    assert client.put(ajuste, json={"status": "COMPLIANT"}).status_code == 422
    client.put(ajuste, json={"status": "COMPLIANT", "justificativa": "Certificado em renovação, protocolo 123"})
    linha = next(l for l in client.get(f"{B}/licitacoes/{lic['id']}/matriz").json()["linhas"] if l["requisito_id"] == reqs["iso"]["id"])
    assert (linha["status"], linha["status_calculado"]) == ("COMPLIANT", "UNKNOWN")
    assert linha["ajuste_manual"]["justificativa"].startswith("Certificado em renovação")


def test_go_no_go_recomenda_explica_e_a_decisao_e_humana(client, criar_usuario_autenticado):
    lic = _licitacao(client)
    rec = client.get(f"{B}/licitacoes/{lic['id']}/go-no-go").json()
    assert rec["recomendacao"] == "INSUFFICIENT_INFORMATION" and len(rec["fatores"]) == 10
    assert all(f["motivo"] and f["status"] for f in rec["fatores"])

    _cofre(client, "Certidão de Regularidade do FGTS", datetime.now(UTC).date() + timedelta(days=3))
    _requisito(client, lic["id"], "HABILITACAO", "Certidão de regularidade do FGTS")
    rec = client.get(f"{B}/licitacoes/{lic['id']}/go-no-go").json()
    assert rec["recomendacao"] == "NO_GO" and rec["bloqueios"]

    vendedor = criar_usuario_autenticado(TENANT, papel="user", email="vendedor@bids.com")
    assert client.post(f"{B}/licitacoes/{lic['id']}/go-no-go", json={"decisao": "GO"}, headers=vendedor).status_code == 403
    assert client.post(f"{B}/licitacoes/{lic['id']}/go-no-go", json={"decisao": "GO"}).status_code == 422
    decisao = client.post(f"{B}/licitacoes/{lic['id']}/go-no-go",
                          json={"decisao": "GO", "justificativa": "Certidão renovada ontem, upload pendente"}).json()
    assert decisao["recomendacao"] == "NO_GO" and decisao["decisao"] == "GO" and len(decisao["fatores"]) == 10
    workspace = client.get(f"{B}/licitacoes/{lic['id']}/workspace").json()
    assert workspace["licitacao"]["status"] == "GO" and workspace["decisoes"][0]["justificativa"]
    assert client.post(f"{B}/licitacoes/{lic['id']}/status", json={"status": "GO"}).status_code == 409


def test_responsavel_da_licitacao_pode_decidir(client, criar_usuario_autenticado, db_session):
    from app.models.usuario import Usuario

    headers = criar_usuario_autenticado(TENANT, papel="user", email="dono@bids.com")
    usuario = db_session.query(Usuario).filter_by(email="dono@bids.com").one()
    lic = _licitacao(client, responsavel_usuario_id=usuario.id)
    resposta = client.post(f"{B}/licitacoes/{lic['id']}/go-no-go", json={"decisao": "NO_GO", "justificativa": "Sem equipe"}, headers=headers)
    assert resposta.status_code == 201


# --- Prazos, cofre, concorrência, contratos -------------------------------------


def test_deadline_engine_junta_proposta_cofre_e_contratos(client):
    lic = _licitacao(client, prazo_proposta=(datetime.now(UTC) + timedelta(days=1)).isoformat())
    _cofre(client, "Balanço 2025", datetime.now(UTC).date())
    hoje = date.today()
    client.post(f"{B}/contratos", json={"objeto": "Licenças", "numero": "CT-1", "vigencia_inicio": (hoje - timedelta(days=300)).isoformat(),
                                        "vigencia_fim": (hoje + timedelta(days=60)).isoformat(), "renovavel": True})

    prazos = client.get(f"{B}/prazos").json()
    tipos = {(p["tipo"], p["nivel"]) for p in prazos}
    assert ("PRAZO_PROPOSTA", "CRITICO") in tipos
    assert ("DOCUMENTO_VENCE_ANTES_DA_PROPOSTA", "CRITICO") in tipos
    assert ("VALIDADE_DOCUMENTO", "CRITICO") in tipos
    assert ("FIM_DE_CONTRATO", "ATENCAO") in tipos
    assert client.get(f"{B}/contratos/sinais").json()[0]["acao"] == "PREPARAR_RENOVACAO"
    assert [a["alerta"] for a in client.get(f"{B}/cofre/alertas").json()] == ["VENCENDO"]
    assert any(p["licitacao_id"] == lic["id"] for p in prazos)


def test_inteligencia_competitiva_so_com_historico_registrado(client):
    a = _licitacao(client, concorrentes=["Alfa Ltda", "Beta SA"])
    b = _licitacao(client, concorrentes=["alfa ltda"])
    client.post(f"{B}/licitacoes/{a['id']}/resultado", json={"ganhou": False, "vencedor": "Alfa Ltda"})
    client.post(f"{B}/licitacoes/{b['id']}/resultado", json={"ganhou": True})

    alfa = next(c for c in client.get(f"{B}/concorrentes").json() if c["concorrente"] == "Alfa Ltda")

    assert (alfa["disputas"], alfa["ganhamos"], alfa["eles_ganharam"], alfa["taxa_vitoria_contra"]) == (2, 1, 1, 0.5)


def test_grafo_de_procurement_e_workspace(client, fake_llm):
    lic = _licitacao(client)
    doc = _enviar(client, lic["id"], _pdf(PAGINA_1, PAGINA_2)).json()
    client.post(f"{B}/licitacoes/{lic['id']}/resultado", json={"ganhou": True})
    client.post(f"{B}/contratos", json={"licitacao_id": lic["id"], "objeto": "Licenças"})

    workspace = client.get(f"{B}/licitacoes/{lic['id']}/workspace").json()
    tipos = {n["tipo"] for n in workspace["grafo"]["nos"]}
    assert {"PUBLIC_ORGANIZATION", "PROCUREMENT_PROCESS", "BID", "PROCUREMENT_DOCUMENT", "RESULT", "PUBLIC_CONTRACT"} <= tipos
    no_doc = next(n for n in workspace["grafo"]["nos"] if n["tipo"] == "PROCUREMENT_DOCUMENT")
    assert no_doc["sha256"] == doc["sha256"]
    assert workspace["contratos"][0]["orgao_nome"] == "Prefeitura X"


# --- Ingestão ------------------------------------------------------------------------

REGISTRO_PNCP = {
    "numeroControlePNCP": "11222333000181-1-000045/2026", "objetoCompra": "Aquisição de licenças de software",
    "valorTotalEstimado": 150000.0, "dataPublicacaoPncp": "2026-09-01T10:00:00", "dataEncerramentoProposta": "2026-10-10T09:00:00",
    "modalidadeId": 6, "srp": False, "anoCompra": 2026, "sequencialCompra": 45,
    "orgaoEntidade": {"cnpj": "11222333000181", "razaoSocial": "MUNICIPIO DE X"},
}


def test_normalizacao_pncp_preserva_fonte_e_link():
    ext = normalizar(REGISTRO_PNCP)
    assert (ext.fonte, ext.id_externo, ext.modalidade, ext.orgao_cnpj) == (
        "PNCP", "11222333000181-1-000045/2026", "PUBLIC_TENDER", "11222333000181")
    assert ext.url == "https://pncp.gov.br/app/editais/11222333000181/2026/45"
    assert normalizar({**REGISTRO_PNCP, "srp": True}).modalidade == "PRICE_REGISTRATION"
    assert normalizar({"objetoCompra": "sem id"}) is None


def test_ingestao_pncp_desligada_por_padrao_e_idempotente_quando_ligada(client, monkeypatch):
    corpo = {"data_inicial": "20260901", "data_final": "20260902"}
    assert client.post(f"{B}/ingestao/pncp", json=corpo).status_code == 409

    def responder(request):
        assert request.url.path.endswith("/contratacoes/publicacao")
        return httpx.Response(200, json={"data": [REGISTRO_PNCP]})

    cliente = httpx.Client(base_url="https://pncp.test/api/consulta/v1", transport=httpx.MockTransport(responder))
    monkeypatch.setattr(settings, "pncp_habilitado", True)
    app.dependency_overrides[get_fonte_pncp] = lambda: FontePncp(cliente)
    try:
        primeira = client.post(f"{B}/ingestao/pncp", json=corpo).json()
        segunda = client.post(f"{B}/ingestao/pncp", json=corpo).json()
    finally:
        app.dependency_overrides.pop(get_fonte_pncp, None)

    assert len(primeira["criadas"]) == 1 and segunda == {"criadas": [], "atualizadas": primeira["criadas"]}
    lic = client.get(f"{B}/licitacoes").json()[0]
    assert lic["fonte"] == "PNCP" and lic["fonte_url"].startswith("https://pncp.gov.br/")
    assert [f["id"] for f in client.get(f"{B}/fontes").json() if f["status"] == "EXPERIMENTAL"] == ["PNCP"]


# --- Fronteiras -------------------------------------------------------------------


def test_modulo_bids_e_exigido(client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"bids"}}))
    assert client.get(f"{B}/licitacoes").status_code == 403
    assert "modulo_bids" in client.get("/api/v1/auth/eu").json()["recursos_plano"]


def test_licitacao_e_documentos_isolados_por_tenant(client, criar_usuario_autenticado):
    lic = _licitacao(client)
    doc = _enviar(client, lic["id"], _pdf(PAGINA_1)).json()
    outro = criar_usuario_autenticado("tenant-outro-bids", papel="admin", email="admin@outro-bids.com")

    assert client.get(f"{B}/licitacoes", headers=outro).json() == []
    for path in (f"/licitacoes/{lic['id']}/workspace", f"/documentos/{doc['id']}/arquivo", f"/licitacoes/{lic['id']}/matriz"):
        assert client.get(B + path, headers=outro).status_code == 404, path
    assert _enviar(client, lic["id"], _pdf("outro"), headers=outro).status_code == 404
    assert client.post(f"{B}/documentos/{doc['id']}/analisar", headers=outro).status_code == 404


@pytest.mark.parametrize("modalidade", ["LEILAO", ""])
def test_modalidade_invalida_recusada(client, modalidade):
    assert client.post(f"{B}/licitacoes", json={"titulo": "abc", "modalidade": modalidade}).status_code == 422
