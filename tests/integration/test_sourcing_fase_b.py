"""Phase B (plano unificado §38): Document & Requirement Engine compartilhado.

Validação pedida: edital público e RFP enterprise passam pelo **mesmo**
engine (e o documento do comprador também), com saída normalizada —
categoria, descrição, evidência literal, fonte, página/cláusula calculadas,
obrigatoriedade lida do trecho (UNKNOWN sem sinal) — e a mesma regra de
proveniência para requisito digitado por humano.
"""

import json

from app.contexts.sourcing import contract as sourcing
from app.models.requisito_licitacao import RequisitoLicitacao
from app.models.sourcing import ProcessoSourcing, RequisitoSourcing

B, P = "/api/v1/bids", "/api/v1/procurement"
EDITAL = ("EDITAL PREGÃO 12/2026\n5.1 A licitante deverá apresentar Certidão Negativa de Débitos Federais.\f"
          "7.3 É desejável certificação ISO 27001.\n8.1 Garantia de cinco anos para os equipamentos.")
RFP = ("REQUEST FOR PROPOSAL — ACME S.A.\n2.1 The vendor must provide 24x7 support with 4-hour response.\f"
       "3.4 Vendors should have a local office in São Paulo.")
CONTRATO = "CONTRATO\nCláusula 3.1 A contratada deverá manter garantia de 36 meses.\fCláusula 9.1 Poderá haver prorrogação."


def _ia(*itens) -> str:
    return json.dumps(list(itens), ensure_ascii=False)


def _licitacao_com_documento(client, modalidade: str, conteudo: str) -> tuple[dict, dict]:
    lic = client.post(f"{B}/licitacoes", json={"titulo": f"Processo {modalidade}", "orgao_nome": "Emissor",
                                               "modalidade": modalidade}).json()
    doc = client.post(f"{B}/licitacoes/{lic['id']}/documentos", data={"tipo": "EDITAL"},
                      files={"arquivo": ("d.txt", conteudo.encode(), "text/plain")}).json()
    return lic, doc


def test_edital_publico_rfp_enterprise_e_documento_do_comprador_no_mesmo_engine(client, db_session, fake_llm, monkeypatch):
    perfis = []
    original = sourcing.requisitos.extrair
    monkeypatch.setattr(sourcing.requisitos, "extrair", lambda *a, **k: perfis.append(a[4].nome) or original(*a, **k))

    publica, doc_publico = _licitacao_com_documento(client, "PUBLIC_TENDER", EDITAL)
    fake_llm.definir_respostas([_ia(
        {"categoria": "HABILITACAO", "descricao": "CND federal", "citacao": "deverá apresentar Certidão Negativa de Débitos Federais",
         "clausula": "5.1"},
        {"categoria": "CERTIFICACAO", "descricao": "ISO 27001", "citacao": "É desejável certificação ISO 27001", "clausula": "7.3"},
        {"categoria": "GARANTIA", "descricao": "Garantia 5 anos", "citacao": "Garantia de cinco anos para os equipamentos"},
        {"categoria": "SLA", "descricao": "Inventado", "citacao": "SLA de 99,99% garantido"},
    )])
    assert client.post(f"{B}/documentos/{doc_publico['id']}/analisar").json()["descartados_sem_evidencia"] == 1

    privada, doc_privado = _licitacao_com_documento(client, "PRIVATE_RFP", RFP)
    fake_llm.definir_respostas([_ia(
        {"categoria": "SLA", "descricao": "Suporte 24x7", "citacao": "The vendor must provide 24x7 support with 4-hour response",
         "clausula": "2.1"},
        {"categoria": "REQUISITO_COMERCIAL", "descricao": "Escritório local", "citacao": "Vendors should have a local office in São Paulo"},
    )])
    client.post(f"{B}/documentos/{doc_privado['id']}/analisar")

    orgao = client.post(f"{P}/orgaos", json={"nome": "Prefeitura"}).json()
    processo = client.post(f"{P}/processos", json={"orgao_id": orgao["id"], "objeto": "Notebooks"}).json()
    doc_compra = client.post(f"{P}/documentos", data={"tipo": "CONTRATO", "processo_id": str(processo["id"])},
                             files={"arquivo": ("c.txt", CONTRATO.encode(), "text/plain")}).json()
    fake_llm.definir_respostas([_ia(
        {"categoria": "GARANTIA", "descricao": "Garantia 36 meses", "citacao": "deverá manter garantia de 36 meses", "clausula": "3.1"},
        {"categoria": "PRAZO", "descricao": "Prorrogação", "citacao": "Poderá haver prorrogação", "clausula": "9.1"},
    )])
    client.post(f"{P}/documentos/{doc_compra['id']}/analisar")

    # mesmo engine, perfil por tipo de documento
    assert perfis == ["edital_tr", "edital_tr", "documento_compras"]

    def normalizados(licitacao_id):
        return [(r["categoria"], r["pagina"], r["clausula"], r["obrigatorio"], r["origem"])
                for r in client.get(f"{B}/licitacoes/{licitacao_id}/requisitos").json()]

    assert normalizados(publica["id"]) == [("HABILITACAO", 1, "5.1", True, "ia"), ("CERTIFICACAO", 2, "7.3", False, "ia"),
                                           ("GARANTIA", 2, None, None, "ia")]  # sem sinal = UNKNOWN; cláusula só se estiver na página
    assert normalizados(privada["id"]) == [("SLA", 1, "2.1", True, "ia"), ("REQUISITO_COMERCIAL", 2, None, False, "ia")]
    achados = client.get(f"{P}/processos/{processo['id']}/workspace").json()["documentos"][0]["achados"]
    assert [(a["pagina"], a["clausula"], a["obrigatorio"]) for a in achados] == [(1, "3.1", True), (2, "9.1", False)]

    # todos chegam ao modelo unificado com a mesma forma, cada um no seu lado e segmento
    def unificados(lado, segmento):
        return {(r.categoria, r.obrigatorio, r.confianca) for r, _ in db_session.query(RequisitoSourcing, ProcessoSourcing)
                .join(ProcessoSourcing, RequisitoSourcing.processo_id == ProcessoSourcing.id)
                .filter(RequisitoSourcing.lado == lado, ProcessoSourcing.segmento == segmento)}

    assert unificados("SELL", "PUBLIC") == {("HABILITACAO", True, "grounded"), ("CERTIFICACAO", False, "grounded"),
                                            ("GARANTIA", None, "grounded")}
    assert unificados("SELL", "ENTERPRISE") == {("SLA", True, "grounded"), ("REQUISITO_COMERCIAL", False, "grounded")}
    assert unificados("BUY", "PUBLIC") == {("GARANTIA", True, "grounded"), ("PRAZO", False, "grounded")}


def test_requisito_manual_usa_a_mesma_regra_de_proveniencia_e_de_obrigatoriedade(client, db_session):
    lic, doc = _licitacao_com_documento(client, "PRIVATE_RFP", RFP)
    url = f"{B}/licitacoes/{lic['id']}/requisitos"

    sem_trecho = client.post(url, json={"categoria": "SLA", "descricao": "Suporte", "documento_id": doc["id"]})
    assert (sem_trecho.status_code, sem_trecho.json()["detalhe"]) == (422, "Informe o trecho do documento que comprova o requisito.")
    inventado = client.post(url, json={"categoria": "SLA", "descricao": "Suporte", "documento_id": doc["id"], "evidencia": "suporte 8x5"})
    assert (inventado.status_code, inventado.json()["detalhe"]) == (422, "O trecho informado não foi encontrado no documento.")

    deduzido = client.post(url, json={"categoria": "SLA", "descricao": "Suporte 24x7", "documento_id": doc["id"],
                                      "evidencia": "must provide 24x7 support"}).json()
    assert (deduzido["pagina"], deduzido["obrigatorio"]) == (1, True)
    informado = client.post(url, json={"categoria": "REQUISITO_COMERCIAL", "descricao": "Escritório", "documento_id": doc["id"],
                                       "evidencia": "should have a local office", "obrigatorio": True}).json()
    assert (informado["pagina"], informado["obrigatorio"]) == (2, True)  # o humano decide
    livre = client.post(url, json={"categoria": "OBRIGACAO", "descricao": "Reunião de kickoff"}).json()
    assert livre["obrigatorio"] is None and livre["pagina"] is None

    linhas = {linha["requisito"]: linha["obrigatorio"] for linha in client.get(f"{B}/licitacoes/{lic['id']}/matriz").json()["linhas"]}
    assert linhas["Suporte 24x7"] is True and linhas["Escritório"] is True
    assert db_session.query(RequisitoLicitacao).filter_by(licitacao_id=lic["id"], obrigatorio=None).count() == 1
