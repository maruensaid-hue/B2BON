"""Phase J1 (preparação da S6): com `sourcing_leitura_fonte = UNIFICADA`, as leituras de listagem vêm das
tabelas unificadas e a API responde **igual** à leitura pelas tabelas antigas (mesmos ids e campos), depois
do backfill. Padrão continua ANTIGA; o lado de quem pergunta nunca vê linha do outro."""

import json
from datetime import UTC, datetime, timedelta

from app.contexts.sourcing import contract as sourcing
from app.core.config import settings

B, P = "/api/v1/bids", "/api/v1/procurement"


def _licitacao(client, titulo, dias) -> dict:
    corpo = {"titulo": titulo, "orgao_nome": "Prefeitura X", "orgao_cnpj": "11222333000181",
             "prazo_proposta": (datetime.now(UTC) + timedelta(days=dias)).isoformat() if dias is not None else None,
             "valor_estimado": 12345.67}
    resposta = client.post(f"{B}/licitacoes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _respostas(client, ids: list[int]) -> dict:
    """Tudo o que as leituras trocáveis alimentam: lista paginada, requisitos (com e sem descartados) e workspace."""
    paginas, cursor = [], None
    while True:
        resposta = client.get(f"{B}/licitacoes", params={"limite": 2, **({"cursor": cursor} if cursor else {})})
        paginas.append(resposta.json())
        cursor = resposta.headers.get("X-Proximo-Cursor")
        if not cursor:
            break
    saida = {"paginas": paginas, "filtradas": client.get(f"{B}/licitacoes", params={"status": "EM_ANALISE"}).json()}
    for i in ids:
        saida[f"requisitos-{i}"] = client.get(f"{B}/licitacoes/{i}/requisitos").json()
        saida[f"todos-{i}"] = client.get(f"{B}/licitacoes/{i}/requisitos", params={"incluir_descartados": True}).json()
        workspace = client.get(f"{B}/licitacoes/{i}/workspace").json()
        workspace["go_no_go"].pop("gerado_em", None)  # hora do cálculo, não dado lido
        saida[f"workspace-{i}"] = {k: workspace[k] for k in ("documentos", "requisitos", "go_no_go")}
    saida["riscos"] = client.get(f"{P}/riscos").json()
    return json.loads(json.dumps(saida, default=str))


def test_leitura_unificada_responde_igual_a_antiga(client, db_session, monkeypatch):
    ids = []
    for titulo, dias in (("Pregão A", 30), ("Pregão B", 10), ("Pregão C", None), ("Pregão D", 10), ("Pregão E", 5)):
        ids.append(_licitacao(client, titulo, dias)["id"])
    client.post(f"{B}/licitacoes/{ids[1]}/status", json={"status": "EM_ANALISE"})
    doc = client.post(f"{B}/licitacoes/{ids[0]}/documentos", data={"tipo": "TR"},
                      files={"arquivo": ("tr.txt", "4.1 O fornecedor deverá prestar suporte 24x7.\f4.2 Relatórios mensais.".encode(),
                                         "text/plain")}).json()
    requisitos = [
        client.post(f"{B}/licitacoes/{ids[0]}/requisitos", json=corpo).json()
        for corpo in ({"categoria": "REQUISITO_TECNICO", "descricao": "Suporte 24x7", "documento_id": doc["id"], "pagina": 1,
                       "evidencia": "O fornecedor deverá prestar suporte 24x7"},
                      {"categoria": "PRAZO", "descricao": "Relatórios mensais"},
                      {"categoria": "GARANTIA", "descricao": "Garantia de um ano"})
    ]
    assert all("id" in r for r in requisitos), requisitos
    assert client.patch(f"{B}/requisitos/{requisitos[2]['id']}", json={"status": "descartado"}).status_code == 200

    sourcing.espelho.sincronizar_todos(db_session)  # o portão da S6: backfill antes de trocar a leitura
    monkeypatch.setattr(settings, "sourcing_leitura_fonte", "ANTIGA")
    antiga = _respostas(client, ids)
    monkeypatch.setattr(settings, "sourcing_leitura_fonte", "UNIFICADA")
    unificada = _respostas(client, ids)

    assert unificada == antiga
    assert len(antiga["paginas"]) == 3 and len(antiga[f"todos-{ids[0]}"]) == 3 and len(antiga[f"requisitos-{ids[0]}"]) == 2
    assert antiga[f"workspace-{ids[0]}"]["documentos"][0]["id"] == doc["id"]  # ids de origem, não os das tabelas novas


def test_padrao_continua_antiga_e_o_lado_comprador_nao_ve_o_vendedor(client, db_session, monkeypatch):
    assert settings.model_fields["sourcing_leitura_fonte"].default == "ANTIGA"
    lic = _licitacao(client, "Pregão só do vendedor", 3)
    sourcing.espelho.sincronizar_todos(db_session)
    monkeypatch.setattr(settings, "sourcing_leitura_fonte", "UNIFICADA")
    vendedor = sourcing.leitura.processos_por_prazo(db_session, sourcing.tipos.Lado.VENDA, "tenant-teste", "licitacao", 50)
    comprador = sourcing.leitura.processos_por_prazo(db_session, sourcing.tipos.Lado.COMPRA, "tenant-teste", "licitacao", 50)
    outro_tenant = sourcing.leitura.processos_por_prazo(db_session, sourcing.tipos.Lado.VENDA, "tenant-outro", "licitacao", 50)
    assert [linha["origem_id"] for linha in vendedor] == [lic["id"]] and comprador == [] and outro_tenant == []
