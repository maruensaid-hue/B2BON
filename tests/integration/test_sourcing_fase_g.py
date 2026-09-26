"""Phase G (plano unificado §43): Intelligence do Strategic Sourcing — TEST grounding.

- Requirement AI: só entra requisito com trecho literal da especificação (página
  calculada, obrigatoriedade lida do trecho); vira sugestão, invisível ao
  fornecedor e fora do processo até a revisão humana. RESTRICTED não vai à IA.
- Evaluation AI: cada proposta numa chamada só com o próprio texto; citação que
  não está na própria proposta (texto do requisito, texto de outro fornecedor,
  requisito inventado) é descartada; nada vira avaliação sem o avaliador.
- Tudo medido: uma execução de crédito por operação, workload do catálogo.
- Supplier Intelligence, riscos e próxima ação: C0, sem IA, com evidência.
- Agente: "Compare as propostas" vai para a ferramenta do comprador.
"""

import json

from app.api.deps import get_plan_limits_provider
from app.main import app
from app.models.registro_uso_ia import RegistroUsoIa
from app.providers.plan_limits.stub import StubPlanLimitsProvider

S, PORTAL, AGENTE = "/api/v1/sourcing", "/api/v1/portal-fornecedor", "/api/v1/inteligencia/agente"
ESPECIFICACAO = (
    "Especificação de suporte de TI.\n"
    "4.1 O fornecedor deverá prestar suporte 24x7 com atendimento em até 4 horas.\n"
    "4.2 Preferencialmente com certificação ISO 27001.\n"
    "\f"
    "5. Perguntas: Qual a garantia oferecida para os equipamentos?\n"
)


def _processo(client, tipo="RFP", titulo="Suporte de TI") -> dict:
    return client.post(f"{S}/processos", json={"tipo_processo": tipo, "titulo": titulo}).json()


def _upload(client, processo, conteudo=ESPECIFICACAO, classificacao="CONFIDENTIAL"):
    return client.post(f"{S}/processos/{processo['id']}/documentos", data={"classificacao": classificacao},
                       files={"arquivo": ("especificacao.txt", conteudo.encode(), "text/plain")})


def _uso(db_session, feature):
    return db_session.query(RegistroUsoIa).filter_by(feature=feature).all()


def test_requirement_ai_so_grava_o_que_esta_no_documento_e_espera_revisao(client, db_session, fake_llm):
    rfp = _processo(client)
    documento = _upload(client, rfp)
    assert documento.status_code == 201 and documento.json()["paginas"] == 2
    assert _upload(client, rfp).status_code == 409  # mesmo arquivo

    fake_llm.definir_respostas([
        json.dumps([
            {"categoria": "SLA", "descricao": "Suporte 24x7 com atendimento em 4 horas",
             "citacao": "O fornecedor deverá prestar suporte 24x7 com atendimento em até 4 horas", "clausula": "4.1"},
            {"categoria": "QUALIFICACAO", "descricao": "Certificação ISO 27001", "citacao": "Preferencialmente com certificação ISO 27001",
             "clausula": "9.9"},
            {"categoria": "GARANTIA", "descricao": "Garantia de 10 anos", "citacao": "garantia mínima de dez anos para todos os itens"},
        ]),
        json.dumps([{"categoria": "PERGUNTA", "descricao": "Qual a garantia oferecida?",
                     "citacao": "Qual a garantia oferecida para os equipamentos?"}]),
    ])
    # as duas páginas cabem num bloco: uma chamada; a segunda resposta da fila não é usada
    analise = client.post(f"{S}/documentos/{documento.json()['id']}/analisar")
    assert analise.status_code == 200, analise.text
    assert (analise.json()["sugeridos"], analise.json()["descartados_sem_evidencia"]) == (2, 1)

    requisitos = {r["texto"]: r for r in client.get(f"{S}/processos/{rfp['id']}/workspace").json()["requisitos"]}
    sla, iso = requisitos["Suporte 24x7 com atendimento em 4 horas"], requisitos["Certificação ISO 27001"]
    assert (sla["fonte"], sla["status_revisao"], sla["pagina"], sla["clausula"], sla["obrigatorio"]) == ("AI", "sugerido", 1, "4.1", True)
    assert (iso["clausula"], iso["obrigatorio"]) == (None, False)  # cláusula que não está na página cai; "preferencialmente" = desejável
    assert "Garantia de 10 anos" not in requisitos

    uso = _uso(db_session, "sourcing.analise_especificacao")
    assert len(uso) == 1 and uso[0].workload_codigo == "procurement_document_intelligence" and uso[0].modulo == "sourcing"

    # sugestão não vale: não publica, não aparece para o fornecedor, não é avaliável
    assert client.post(f"{S}/processos/{rfp['id']}/status", json={"status": "PUBLICADO"}).status_code == 409
    assert client.put(f"{S}/requisitos/{iso['id']}/revisao", json={"confirmar": False}).status_code == 200
    confirmado = client.put(f"{S}/requisitos/{sla['id']}/revisao", json={"confirmar": True, "peso": 2})
    assert confirmado.json()["status_revisao"] == "confirmado" and confirmado.json()["peso"] == 2
    assert client.put(f"{S}/requisitos/{sla['id']}/revisao", json={"confirmar": True}).status_code == 409  # já revisado
    ws = client.get(f"{S}/processos/{rfp['id']}/workspace").json()
    assert [r["texto"] for r in ws["requisitos"]] == ["Suporte 24x7 com atendimento em 4 horas"]  # descartado some
    assert ws["documentos"][0]["status_extracao"] == "ANALISADO"

    alfa = client.post(f"{S}/processos/{rfp['id']}/participantes", json={"nome": "Fornecedor Alfa"}).json()
    token = client.post(f"{S}/processos/{rfp['id']}/participantes/{alfa['id']}/acesso", json={}).json()["token"]
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        assert client.post(f"{S}/processos/{rfp['id']}/status", json={"status": status}).status_code == 200
    visao = client.get(PORTAL, headers={"X-Convite-Token": token}).json()
    assert [r["texto"] for r in visao["requisitos"]] == ["Suporte 24x7 com atendimento em 4 horas"]
    assert "ISO 27001" not in json.dumps(visao) and "trecho" not in visao["requisitos"][0]
    # com o processo recebendo propostas, a especificação não gera mais requisitos
    assert client.post(f"{S}/documentos/{documento.json()['id']}/analisar").status_code == 409


def test_documento_restrito_nao_vai_para_a_ia_e_outro_tenant_nao_ve(client, db_session, fake_llm, criar_usuario_autenticado):
    rfp = _processo(client)
    restrito = _upload(client, rfp, classificacao="RESTRICTED").json()
    resposta = client.post(f"{S}/documentos/{restrito['id']}/analisar")
    assert resposta.status_code == 409 and "RESTRICTED" in resposta.json()["detalhe"]
    assert fake_llm.chamadas == [] and _uso(db_session, "sourcing.analise_especificacao") == []
    outro = criar_usuario_autenticado("tenant-outro")
    assert client.get(f"{S}/documentos/{restrito['id']}/arquivo", headers=outro).status_code == 404
    assert client.get(f"{S}/documentos/{restrito['id']}/arquivo").content == ESPECIFICACAO.encode()


def _rfp_com_propostas(client) -> tuple[dict, dict, dict, dict]:
    rfp = _processo(client, titulo="Notebooks")
    url = f"{S}/processos/{rfp['id']}"
    ram = client.post(f"{url}/requisitos", json={"categoria": "REQUISITO_TECNICO", "texto": "16 GB de RAM", "obrigatorio": True}).json()
    garantia = client.post(f"{url}/requisitos", json={"categoria": "GARANTIA", "texto": "Garantia de 36 meses"}).json()
    alfa = client.post(f"{url}/participantes", json={"nome": "Fornecedor Alfa"}).json()
    beta = client.post(f"{url}/participantes", json={"nome": "Fornecedor Beta"}).json()
    token_beta = client.post(f"{url}/participantes/{beta['id']}/acesso", json={}).json()["token"]
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        client.post(f"{url}/status", json={"status": status})
    client.post(f"{url}/propostas", json={
        "participante_id": alfa["id"], "valor_total": 50000, "observacoes": "SEGREDO-ALFA-778 desconto exclusivo",
        "respostas": [{"requisito_id": ram["id"], "resposta": "Nossos notebooks vêm com 32 GB de RAM DDR5"}]})
    enviada = client.post(f"{PORTAL}/propostas", headers={"X-Convite-Token": token_beta}, json={
        "valor_total": 42000, "respostas": [{"requisito_id": ram["id"], "resposta": "Modelo padrão com 8 GB de memória"}]}).json()
    client.post(f"{PORTAL}/propostas/{enviada['id']}/anexos", headers={"X-Convite-Token": token_beta},
                files={"arquivo": ("garantia.txt", b"Termo: garantia de 12 meses on-site", "text/plain")})
    return rfp, {"ram": ram, "garantia": garantia}, alfa, beta


def test_evaluation_ai_ancora_na_propria_proposta_e_nao_grava(client, db_session, fake_llm):
    rfp, req, alfa, beta = _rfp_com_propostas(client)
    url = f"{S}/processos/{rfp['id']}"
    assert client.post(f"{url}/avaliacao-ia").status_code == 409  # ainda recebendo propostas
    client.post(f"{url}/status", json={"status": "EM_AVALIACAO"})
    fake_llm.chamadas.clear()
    fake_llm.definir_respostas([
        json.dumps([  # Alfa
            {"requisito_id": req["ram"]["id"], "status": "COMPLIANT", "citacao": "vêm com 32 GB de RAM DDR5", "justificativa": "Acima do mínimo"},
            {"requisito_id": req["garantia"]["id"], "status": "COMPLIANT", "citacao": "Garantia de 36 meses"},  # texto do requisito
            {"requisito_id": 99999, "status": "COMPLIANT", "citacao": "32 GB de RAM DDR5"},  # requisito inventado
        ]),
        json.dumps([  # Beta
            {"requisito_id": req["ram"]["id"], "status": "NON_COMPLIANT", "citacao": "Modelo padrão com 8 GB de memória"},
            {"requisito_id": req["garantia"]["id"], "status": "PARTIALLY_COMPLIANT", "citacao": "garantia de 12 meses on-site"},  # anexo
            {"requisito_id": req["ram"]["id"], "status": "COMPLIANT", "citacao": "32 GB de RAM DDR5"},  # texto do Alfa
        ]),
    ])
    resposta = client.post(f"{url}/avaliacao-ia")
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert (corpo["propostas_analisadas"], corpo["descartadas_sem_evidencia"]) == (2, 3)
    assert {(s["participante_id"], s["requisito_id"], s["status"]) for s in corpo["sugestoes"]} == {
        (alfa["id"], req["ram"]["id"], "COMPLIANT"), (beta["id"], req["ram"]["id"], "NON_COMPLIANT"),
        (beta["id"], req["garantia"]["id"], "PARTIALLY_COMPLIANT")}

    # barreira entre fornecedores: cada chamada leva só a própria proposta
    prompt_alfa, prompt_beta = (c.prompt for c in fake_llm.chamadas)
    assert "SEGREDO-ALFA-778" in prompt_alfa and "8 GB" not in prompt_alfa
    assert "SEGREDO-ALFA-778" not in prompt_beta and "32 GB" not in prompt_beta and "12 meses on-site" in prompt_beta

    # uma execução de crédito para a operação inteira, no workload do catálogo
    uso = _uso(db_session, "sourcing.avaliacao_propostas")
    assert len(uso) == 2 and len({u.execucao_id for u in uso}) == 1 and uso[0].workload_codigo == "procurement_complex_comparison"
    # nada virou avaliação: quem decide é o avaliador
    avaliacoes = [a for p in client.get(f"{url}/workspace").json()["propostas"] for a in p["avaliacoes"]]
    assert all(a["status"] is None for a in avaliacoes)


def test_inteligencia_c0_alertas_proxima_acao_e_historico(client, db_session, fake_llm):
    anterior = _processo(client, "RFQ", "Cadeiras 2025")
    url_anterior = f"{S}/processos/{anterior['id']}"
    client.post(f"{url_anterior}/itens", json={"descricao": "Cadeira", "quantidade": 1})
    delta_antes = client.post(f"{url_anterior}/participantes", json={"nome": "Móveis Delta"}).json()
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        client.post(f"{url_anterior}/status", json={"status": status})
    client.put(f"{url_anterior}/participantes/{delta_antes['id']}", json={"status": "DESQUALIFICADO", "motivo": "Documentação vencida"})

    rfq = _processo(client, "RFQ", "Cadeiras 2026")
    url = f"{S}/processos/{rfq['id']}"
    assert client.get(f"{url}/workspace").json()["inteligencia"]["proxima_acao"]["acao"] == "CADASTRAR_REQUISITOS"
    client.post(f"{url}/itens", json={"descricao": "Cadeira", "quantidade": 1})
    ids = [client.post(f"{url}/participantes", json={"nome": n}).json()["id"] for n in ("Móveis Delta", "Móveis Eta", "Móveis Zeta")]
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        client.post(f"{url}/status", json={"status": status})
    for pid, valor in zip(ids, (100, 110, 50), strict=True):
        client.post(f"{url}/propostas", json={"participante_id": pid, "valor_total": valor})

    ws = client.get(f"{url}/workspace").json()
    delta = next(p for p in ws["participantes"] if p["id"] == ids[0])
    assert delta["historico"] == {"processos": 1, "respondeu": 0, "declinou": 0, "adjudicado": 0, "desqualificado": 1}
    alertas = {(a["tipo"], a["evidencia"].get("participante_id")): a for a in ws["inteligencia"]["alertas"]}
    assert alertas[("PRECO_MUITO_ABAIXO", ids[2])]["evidencia"] == {"participante_id": ids[2], "valor": 50.0, "mediana": 100.0}
    assert ("HISTORICO_FORNECEDOR", ids[0]) in alertas
    assert ws["inteligencia"]["proxima_acao"]["acao"] == "DECIDIR"  # RFQ: todos cotaram, vai direto à aprovação
    assert fake_llm.chamadas == [] and db_session.query(RegistroUsoIa).count() == 0  # C0: sem IA, sem crédito

    # agente: a pergunta do comprador vai para a ferramenta do lado comprador, sem IA
    comparacao = client.post(AGENTE, json={"pergunta": f"Compare as propostas do processo {rfq['id']}"}).json()
    assert (comparacao["status"], comparacao["ferramenta"], comparacao["agente"]) == (
        "OK", "sourcing.comparar_propostas", "procurement_intelligence_agent")  # D-055: capability, sem agente novo
    assert comparacao["resultado"]["destaques"]["menor_valor"] == ids[2]
    historico = client.post(AGENTE, json={"pergunta": "Qual o histórico do fornecedor Móveis Delta?"}).json()
    assert historico["ferramenta"] == "sourcing.historico_fornecedor"
    assert historico["resultado"]["fornecedores"][0]["processos"] == 2
    pendencias = client.post(AGENTE, json={"pergunta": "Quais processos de sourcing precisam de atenção?"}).json()
    assert pendencias["ferramenta"] == "sourcing.pendencias" and len(pendencias["resultado"]["processos"]) == 2
    assert fake_llm.chamadas == []


def test_ferramentas_de_sourcing_exigem_o_modulo(client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={"tenant-teste": {"sourcing"}}))
    catalogo = client.get("/api/v1/inteligencia/agente/ferramentas").json()
    assert not [f for f in catalogo if f["ferramenta"].startswith("sourcing.")]
