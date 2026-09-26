"""Sourcing S4 pela API: as mesmas respostas de antes, agora vindas do workflow declarativo."""

import pytest

B, P = "/api/v1/bids", "/api/v1/procurement"
MSG_GO = "GO/NO_GO é registrado pela decisão Go/No-Go, com a recomendação e a justificativa."
MSG_RESULTADO = "Use o registro de resultado para informar vencedor e valor."


@pytest.mark.parametrize("modalidade", ["PUBLIC_TENDER", "PRIVATE_RFP"])
def test_status_da_licitacao_responde_como_antes(client, modalidade):
    lic = client.post(f"{B}/licitacoes", json={"titulo": "Edital S4", "objeto": "Notebooks", "modalidade": modalidade,
                                                "orgao_nome": "Órgão"}).json()
    assert lic["status"] == "IDENTIFICADA"
    url = f"{B}/licitacoes/{lic['id']}"
    for status in ("EM_ANALISE", "PROPOSTA_ENVIADA", "CANCELADA", "IDENTIFICADA", "EM_ANALISE"):  # qualquer → qualquer
        resposta = client.post(f"{url}/status", json={"status": status})
        assert resposta.status_code == 200 and resposta.json()["status"] == status
    for status, mensagem in (("GO", MSG_GO), ("NO_GO", MSG_GO), ("GANHA", MSG_RESULTADO), ("PERDIDA", MSG_RESULTADO)):
        resposta = client.post(f"{url}/status", json={"status": status})
        assert (resposta.status_code, resposta.json()["detalhe"]) == (409, mensagem)
    resposta = client.post(f"{url}/status", json={"status": "INVENTADO"})
    assert (resposta.status_code, resposta.json()["detalhe"]) == (422, "Status inválido: INVENTADO")

    assert client.post(f"{url}/resultado", json={"ganhou": False, "vencedor": "Concorrente"}).json()["status"] == "PERDIDA"
    assert client.post(f"{url}/resultado", json={"ganhou": True}).json()["status"] == "GANHA"  # de qualquer estado, como antes
    assert client.post(f"{url}/status", json={"status": "EM_ANALISE"}).status_code == 200
    decisao = client.post(f"{url}/go-no-go", json={"decisao": "NO_GO", "justificativa": "Sem equipe"})
    assert decisao.status_code == 201
    assert client.get(f"{url}/workspace").json()["licitacao"]["status"] == "NO_GO"
    assert client.post(f"{url}/go-no-go", json={"decisao": "TALVEZ"}).status_code == 422  # recusado já no esquema


def test_status_do_processo_de_compra_responde_como_antes(client):
    orgao = client.post(f"{P}/orgaos", json={"nome": "Prefeitura"}).json()
    proc = client.post(f"{P}/processos", json={"orgao_id": orgao["id"], "objeto": "Limpeza"}).json()
    assert proc["status"] == "PLANEJAMENTO"
    url = f"{P}/processos/{proc['id']}"
    for status in ("PUBLICADO", "PLANEJAMENTO", "CONTRATADO", "SELECAO"):
        resposta = client.patch(url, json={"status": status})
        assert resposta.status_code == 200 and resposta.json()["status"] == status
    resposta = client.patch(url, json={"status": "INVENTADA"})
    assert (resposta.status_code, resposta.json()["detalhe"]) == (422, "Status inválido: INVENTADA")
