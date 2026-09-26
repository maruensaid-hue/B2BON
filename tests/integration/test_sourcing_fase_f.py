"""Phase F (plano unificado §42): Business Network e acesso do fornecedor — confidencialidade.

- Link secreto sem login e sem assento (Supplier Guest): só o hash é guardado,
  o segredo não passa pelo caminho da URL (nem pelo log), gerar de novo revoga.
- O fornecedor vê só o próprio convite: sem peso, valor estimado, avaliações,
  aprovação ou outros participantes; esclarecimentos saem sem dizer quem perguntou.
- Empresa da rede responde pela própria conta e só vê os convites dela.
- Proposta e anexos pelo portal chegam ao comprador; nada disso usa IA.
"""

import logging

from app.models.perfil_empresa import PerfilEmpresa
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.sourcing import ParticipanteSourcing
from app.models.tenant import Tenant
from app.models.usuario import Usuario

S, PORTAL, REDE = "/api/v1/sourcing", "/api/v1/portal-fornecedor", "/api/v1/rede/convites-sourcing"
TENANT = "tenant-teste"
SEGREDO_COMPRADOR = "OBSERVACAO-INTERNA-DO-COMPRADOR-5521"


def _rfp(client) -> tuple[dict, dict, dict, dict]:
    rfp = client.post(f"{S}/processos", json={"tipo_processo": "RFP", "titulo": "Notebooks corporativos",
                                              "descricao": "Renovação do parque", "valor_estimado": 987654}).json()
    url = f"{S}/processos/{rfp['id']}"
    requisito = client.post(f"{url}/requisitos", json={"categoria": "REQUISITO_TECNICO", "texto": "16 GB de RAM", "obrigatorio": True,
                                                      "peso": 3}).json()
    pergunta = client.post(f"{url}/requisitos", json={"categoria": "PERGUNTA", "texto": "Qual a garantia?"}).json()
    alfa = client.post(f"{url}/participantes", json={"nome": "Fornecedor Alfa"}).json()
    beta = client.post(f"{url}/participantes", json={"nome": "Fornecedor Beta"}).json()
    return rfp, {"requisito": requisito, "pergunta": pergunta}, alfa, beta


def _link(client, rfp, participante) -> str:
    resposta = client.post(f"{S}/processos/{rfp['id']}/participantes/{participante['id']}/acesso", json={"email": "a@alfa.com"})
    assert resposta.status_code == 200 and resposta.json()["caminho"].startswith("/portal-fornecedor#")
    return resposta.json()["token"]


def _abrir(client, rfp) -> None:
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        client.post(f"{S}/processos/{rfp['id']}/status", json={"status": status})


def test_fornecedor_por_link_ve_so_o_proprio_convite_e_responde(client, db_session, fake_llm, caplog):
    rfp, req, alfa, beta = _rfp(client)
    token_alfa, token_beta = _link(client, rfp, alfa), _link(client, rfp, beta)
    h_alfa, h_beta = {"X-Convite-Token": token_alfa}, {"X-Convite-Token": token_beta}
    usuarios_antes = db_session.query(Usuario).filter_by(tenant_id=TENANT).count()

    assert client.get(PORTAL, headers=h_alfa).status_code == 404  # rascunho: o convite ainda não existe para o fornecedor
    _abrir(client, rfp)
    caplog.set_level(logging.INFO)
    visao = client.get(PORTAL, headers=h_alfa)
    assert visao.status_code == 200
    corpo = visao.json()
    assert corpo["processo"]["situacao"] == "ABERTO" and corpo["participacao"]["pode_enviar"] is True
    assert corpo["requisitos"][0] == {"id": req["requisito"]["id"], "categoria": "REQUISITO_TECNICO", "texto": "16 GB de RAM",
                                      "obrigatorio": True}  # sem peso
    texto = visao.text
    assert "987654" not in texto and "Fornecedor Beta" not in texto and "peso" not in texto
    assert token_alfa not in caplog.text  # o segredo não aparece no log de acesso

    assert client.post(f"{PORTAL}/perguntas", json={"pergunta": "Aceitam 12 GB?"}, headers=h_alfa).status_code == 201
    esclarecimento = client.get(f"{S}/processos/{rfp['id']}/workspace").json()["esclarecimentos"][0]
    assert esclarecimento["participante_id"] == alfa["id"]  # o comprador sabe quem perguntou
    client.put(f"{S}/esclarecimentos/{esclarecimento['id']}", json={"resposta": "Não. Mínimo de 16 GB."})
    vista_beta = client.get(PORTAL, headers=h_beta).json()
    assert vista_beta["esclarecimentos"] == [{"pergunta": "Aceitam 12 GB?", "resposta": "Não. Mínimo de 16 GB.",
                                              "respondido_em": vista_beta["esclarecimentos"][0]["respondido_em"]}]
    assert vista_beta["minhas_perguntas"] == [] and "Fornecedor Alfa" not in str(vista_beta)  # sem dizer quem perguntou

    proposta = client.post(f"{PORTAL}/propostas", headers=h_alfa, json={
        "valor_total": 50000, "prazo_entrega_dias": 20, "respostas": [{"requisito_id": req["pergunta"]["id"], "resposta": "36 meses"}]})
    assert proposta.status_code == 201 and proposta.json()["rodada"] == 1
    anexo = client.post(f"{PORTAL}/propostas/{proposta.json()['id']}/anexos", headers=h_alfa,
                        files={"arquivo": ("atestado.txt", b"Atestado de capacidade tecnica", "text/plain")})
    assert anexo.status_code == 201
    invalido = client.post(f"{PORTAL}/propostas/{proposta.json()['id']}/anexos", headers=h_alfa,
                           files={"arquivo": ("x.exe", b"MZ....", "application/octet-stream")})
    assert invalido.status_code == 422
    alheia = client.post(f"{PORTAL}/propostas/{proposta.json()['id']}/anexos", headers=h_beta,
                         files={"arquivo": ("b.txt", b"tentativa", "text/plain")})
    assert alheia.status_code == 404  # não anexa em proposta de outro fornecedor

    ws = client.get(f"{S}/processos/{rfp['id']}/workspace").json()
    assert ws["propostas"][0]["canal"] == "PORTAL" and ws["anexos"][0]["nome_arquivo"] == "atestado.txt"
    baixado = client.get(f"{S}/anexos/{ws['anexos'][0]['id']}")
    assert baixado.content == b"Atestado de capacidade tecnica"

    client.post(f"{S}/processos/{rfp['id']}/status", json={"status": "EM_AVALIACAO"})
    client.put(f"{S}/propostas/{proposta.json()['id']}/avaliacoes", json={
        "requisito_id": req["requisito"]["id"], "status": "NON_COMPLIANT", "nota": 1, "justificativa": SEGREDO_COMPRADOR})
    depois = client.get(PORTAL, headers=h_alfa)
    assert depois.json()["processo"]["situacao"] == "EM_ANALISE" and depois.json()["participacao"]["pode_enviar"] is False
    assert SEGREDO_COMPRADOR not in depois.text and "NON_COMPLIANT" not in depois.text
    assert client.post(f"{PORTAL}/propostas", headers=h_alfa, json={"valor_total": 1}).status_code == 409

    # sem assento, sem IA
    assert db_session.query(Usuario).filter_by(tenant_id=TENANT).count() == usuarios_antes
    assert fake_llm.chamadas == [] and db_session.query(RegistroUsoIa).count() == 0


def test_link_invalido_revogado_e_so_hash_guardado(client, db_session):
    rfp, _, alfa, _ = _rfp(client)
    _abrir(client, rfp)
    antigo = _link(client, rfp, alfa)
    novo = _link(client, rfp, alfa)
    guardado = db_session.query(ParticipanteSourcing).filter_by(id=alfa["id"]).one().token_hash
    assert guardado not in (antigo, novo) and len(guardado) == 64  # hash, nunca o segredo
    for token in (antigo, "inventado", ""):
        resposta = client.get(PORTAL, headers={"X-Convite-Token": token})
        assert (resposta.status_code, resposta.json()["detalhe"]) == (404, "Convite não encontrado.")
    assert client.get(PORTAL, headers={"X-Convite-Token": novo}).status_code == 200


def test_negociacao_e_declinio_pelo_portal(client):
    rfp, _, alfa, beta = _rfp(client)
    h_alfa, h_beta = {"X-Convite-Token": _link(client, rfp, alfa)}, {"X-Convite-Token": _link(client, rfp, beta)}
    _abrir(client, rfp)
    client.post(f"{PORTAL}/propostas", headers=h_alfa, json={"valor_total": 100})
    client.post(f"{PORTAL}/propostas", headers=h_beta, json={"valor_total": 90})
    url = f"{S}/processos/{rfp['id']}"
    client.post(f"{url}/status", json={"status": "EM_AVALIACAO"})
    client.put(f"{url}/participantes/{alfa['id']}", json={"status": "SHORTLIST"})
    client.post(f"{url}/status", json={"status": "EM_NEGOCIACAO"})
    assert client.get(PORTAL, headers=h_alfa).json()["processo"]["situacao"] == "EM_NEGOCIACAO"
    assert client.get(PORTAL, headers=h_beta).json()["processo"]["situacao"] == "EM_ANALISE"  # não sabe que há negociação
    assert client.post(f"{PORTAL}/propostas", headers=h_beta, json={"valor_total": 80}).status_code == 409
    assert client.post(f"{PORTAL}/propostas", headers=h_alfa, json={"valor_total": 95}).json()["rodada"] == 2
    assert client.post(f"{PORTAL}/declinar", headers=h_beta, json={"motivo": "Sem estoque"}).json()["situacao"] == "DECLINOU"
    assert client.get(f"{url}/workspace").json()["participantes"][1]["status"] == "DECLINOU"


def test_empresa_da_rede_responde_pela_conta_e_so_ve_os_seus_convites(client, db_session, criar_usuario_autenticado):
    db_session.add(Tenant(id="rede-fornecedor", razao_social="Fornecedor da Rede Ltda"))
    db_session.add(PerfilEmpresa(tenant_id="rede-fornecedor", nome_exibicao="Fornecedor da Rede", produtos_servicos=["Notebooks"]))
    db_session.commit()
    rfp = client.post(f"{S}/processos", json={"tipo_processo": "RFQ", "titulo": "Cotação de notebooks"}).json()
    url = f"{S}/processos/{rfp['id']}"
    item = client.post(f"{url}/itens", json={"descricao": "Notebook", "quantidade": 2}).json()
    convite = client.post(f"{url}/participantes", json={"empresa_rede_tenant_id": "rede-fornecedor"}).json()
    fornecedor = criar_usuario_autenticado("rede-fornecedor", papel="user", email="vendas@fornecedor.com")
    outro = criar_usuario_autenticado("tenant-curioso", papel="admin", email="x@curioso.com")

    assert client.get(REDE, headers=fornecedor).json() == []  # rascunho não aparece
    for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
        client.post(f"{url}/status", json={"status": status})
    convites = client.get(REDE, headers=fornecedor).json()
    assert [(c["participante_id"], c["titulo"], c["situacao"]) for c in convites] == [(convite["id"], "Cotação de notebooks", "ABERTO")]
    assert convites[0]["comprador"] == db_session.get(Tenant, TENANT).razao_social
    assert client.get(REDE, headers=outro).json() == []
    assert client.get(f"{REDE}/{convite['id']}", headers=outro).status_code == 404

    enviada = client.post(f"{REDE}/{convite['id']}/propostas", headers=fornecedor,
                          json={"itens": [{"item_id": item["id"], "preco_unitario": 4500}]})
    assert enviada.status_code == 201 and enviada.json()["valor_total"] == 9000.0
    visao = client.get(f"{REDE}/{convite['id']}", headers=fornecedor).json()
    assert visao["minhas_propostas"][0]["valor_total"] == 9000.0 and visao["participacao"]["situacao"] == "RESPONDEU"
    # o convite não vira dado do lado vendedor da empresa convidada
    assert client.get("/api/v1/bids/licitacoes", headers=fornecedor).json() == []
