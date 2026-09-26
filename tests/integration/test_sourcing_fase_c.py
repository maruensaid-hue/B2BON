"""Phase C (plano unificado §39): lado vendedor — Public Bid + Enterprise Bid.

- Enterprise Bid por configuração: modalidades privadas (RFI, RFQ,
  concorrência privada) no segmento ENTERPRISE, workflow v2 com negociação
  só depois da proposta enviada; o público não tem negociação.
- Tela sem estados fixos: o workspace diz o que dá para fazer agora.
- Resposta por requisito/pergunta; esboço de proposta determinístico (sem IA).
- Go/No-Go v2: obrigatório não atendido bloqueia; desejável não.
"""

from datetime import UTC, datetime, timedelta

from app.models.registro_uso_ia import RegistroUsoIa
from app.models.sourcing import ProcessoSourcing

B = "/api/v1/bids"


def _licitacao(client, modalidade: str, **extra) -> dict:
    corpo = {"titulo": f"Processo {modalidade}", "orgao_nome": "ACME S.A.", "modalidade": modalidade, **extra}
    resposta = client.post(f"{B}/licitacoes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _fluxo(client, licitacao_id: int) -> dict:
    return client.get(f"{B}/licitacoes/{licitacao_id}/workspace").json()["fluxo"]


def test_enterprise_bid_do_recebimento_ao_resultado_com_negociacao(client, db_session):
    lic = _licitacao(client, "PRIVATE_RFQ")
    processo = db_session.query(ProcessoSourcing).filter_by(origem_tabela="licitacao", origem_id=lic["id"]).one()
    assert (processo.segmento, processo.tipo_processo, processo.workflow) == ("ENTERPRISE", "RFQ", "ENTERPRISE_RFP_SELL@2")

    fluxo = _fluxo(client, lic["id"])
    assert fluxo["segmento"] == "ENTERPRISE" and "EM_NEGOCIACAO" not in fluxo["proximos_status"]
    assert fluxo["proximos_status"] == ["EM_ANALISE", "PROPOSTA_ENVIADA", "CANCELADA"]
    url = f"{B}/licitacoes/{lic['id']}"
    cedo = client.post(f"{url}/status", json={"status": "EM_NEGOCIACAO"})
    assert (cedo.status_code, cedo.json()["detalhe"]) == (409, "Transição não permitida: IDENTIFICADA → EM_NEGOCIACAO.")

    pergunta = client.post(f"{url}/requisitos", json={"categoria": "PERGUNTA", "descricao": "Qual o prazo de entrega?"}).json()
    respondida = client.put(f"{B}/requisitos/{pergunta['id']}/resposta", json={"resposta": "  15 dias corridos  "}).json()
    assert respondida["resposta"] == "15 dias corridos"
    assert client.post(f"{url}/status", json={"status": "PROPOSTA_ENVIADA"}).status_code == 200
    assert "EM_NEGOCIACAO" in _fluxo(client, lic["id"])["proximos_status"]
    assert client.post(f"{url}/status", json={"status": "EM_NEGOCIACAO"}).json()["status"] == "EM_NEGOCIACAO"
    assert client.post(f"{url}/resultado", json={"ganhou": True, "valor_proposta": 50000}).json()["status"] == "GANHA"
    assert _fluxo(client, lic["id"])["final"] is True


def test_licitacao_publica_nao_tem_negociacao_e_segue_ate_o_contrato(client):
    lic = _licitacao(client, "PUBLIC_TENDER", orgao_nome="Prefeitura")
    url = f"{B}/licitacoes/{lic['id']}"
    assert "EM_NEGOCIACAO" not in _fluxo(client, lic["id"])["proximos_status"]
    negociar = client.post(f"{url}/status", json={"status": "EM_NEGOCIACAO"})
    assert (negociar.status_code, negociar.json()["detalhe"]) == (422, "Status inválido: EM_NEGOCIACAO")
    client.post(f"{url}/status", json={"status": "PROPOSTA_ENVIADA"})
    assert _fluxo(client, lic["id"])["aceita_resultado"] is True
    client.post(f"{url}/resultado", json={"ganhou": True, "vencedor": "Nós"})
    contrato = client.post(f"{B}/contratos", json={"licitacao_id": lic["id"], "objeto": "Fornecimento", "valor": 1000})
    assert contrato.status_code == 201, contrato.text


def test_go_no_go_v2_obrigatorio_nao_atendido_bloqueia_desejavel_nao(client):
    lic = _licitacao(client, "PRIVATE_RFP")
    url = f"{B}/licitacoes/{lic['id']}"

    def requisito(descricao, obrigatorio):
        req = client.post(f"{url}/requisitos", json={"categoria": "REQUISITO_TECNICO", "descricao": descricao,
                                                     "obrigatorio": obrigatorio}).json()
        client.put(f"{B}/requisitos/{req['id']}/conformidade", json={"status": "NON_COMPLIANT", "justificativa": "Não temos"})
        return req

    requisito("Painel em braile", False)
    recomendacao = client.get(f"{url}/go-no-go").json()
    assert not any("obrigatório" in b for b in recomendacao["bloqueios"]) and recomendacao["fonte"] == "bids.go_no_go.v2"

    requisito("Suporte 24x7 em Manaus", True)
    recomendacao = client.get(f"{url}/go-no-go").json()
    assert recomendacao["recomendacao"] == "NO_GO"
    assert "1 requisito(s) técnico(s)/comercial(is) obrigatório(s) não atendido(s)." in recomendacao["bloqueios"]
    tecnico = next(f for f in recomendacao["fatores"] if f["fator"] == "Technical Fit")
    assert tecnico["status"] == "DESFAVORAVEL" and "1 obrigatório(s) não atendido(s)" in tecnico["motivo"]


def test_esboco_de_proposta_sem_ia_com_pendencias_anexos_e_markdown(client, db_session, fake_llm):
    lic = _licitacao(client, "PRIVATE_RFI", prazo_proposta=(datetime.now(UTC) + timedelta(days=10)).isoformat())
    url = f"{B}/licitacoes/{lic['id']}"
    client.post(f"{B}/cofre", data={"tipo": "CERTIDAO", "nome": "Certidão Negativa de Débitos Federais",
                                    "valido_ate": (datetime.now(UTC).date() + timedelta(days=60)).isoformat()},
                files={"arquivo": ("c.pdf", b"%PDF-1.4 certidao", "application/pdf")})
    certidao = client.post(f"{url}/requisitos", json={"categoria": "HABILITACAO", "descricao": "Certidão negativa de débitos federais",
                                                      "obrigatorio": True}).json()
    pergunta = client.post(f"{url}/requisitos", json={"categoria": "PERGUNTA", "descricao": "Descreva sua equipe"}).json()
    suporte = client.post(f"{url}/requisitos", json={"categoria": "SLA", "descricao": "Suporte em Manaus", "obrigatorio": True}).json()
    chamadas = len(fake_llm.chamadas)

    esboco = client.get(f"{url}/proposta").json()

    assert esboco["licitacao"]["tipo_processo"] == "RFI" and esboco["licitacao"]["segmento"] == "ENTERPRISE"
    pendencias = {(p["requisito_id"], p["tipo"]) for p in esboco["pendencias"]}
    assert pendencias == {(pergunta["id"], "RESPONDER"), (suporte["id"], "COMPROVAR")}
    assert [a["nome"] for a in esboco["anexos"]] == ["Certidão Negativa de Débitos Federais"]
    assert certidao["id"] not in {p["requisito_id"] for p in esboco["pendencias"]}
    assert esboco["prontidao"] == 0.33 and esboco["fonte"] == "bids.proposta.v1"

    client.put(f"{B}/requisitos/{pergunta['id']}/resposta", json={"resposta": "Cinco engenheiros certificados"})
    markdown = client.get(f"{url}/proposta?formato=markdown")
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Resposta: Cinco engenheiros certificados" in markdown.text and "- [ ] Obrigatório sem comprovação" in markdown.text
    assert "## Documentos a anexar (cofre)" in markdown.text
    # C0: nenhuma chamada de IA, nenhum crédito
    assert len(fake_llm.chamadas) == chamadas and db_session.query(RegistroUsoIa).count() == 0


def test_resposta_respeita_revisao_e_tenant(client, criar_usuario_autenticado):
    lic = _licitacao(client, "PRIVATE_TENDER")
    req = client.post(f"{B}/licitacoes/{lic['id']}/requisitos", json={"categoria": "OBRIGACAO", "descricao": "Kickoff"}).json()
    client.patch(f"{B}/requisitos/{req['id']}", json={"status": "descartado"})
    descartado = client.put(f"{B}/requisitos/{req['id']}/resposta", json={"resposta": "x"})
    assert (descartado.status_code, descartado.json()["detalhe"]) == (409, "Requisito descartado não recebe resposta.")

    outro = criar_usuario_autenticado("tenant-outro")
    assert client.get(f"{B}/licitacoes/{lic['id']}/proposta", headers=outro).status_code in (403, 404)
    assert client.put(f"{B}/requisitos/{req['id']}/resposta", json={"resposta": "x"}, headers=outro).status_code in (403, 404)
