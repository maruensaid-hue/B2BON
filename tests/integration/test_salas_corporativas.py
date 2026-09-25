"""Corporate Rooms & Buying Rooms (Fase 11). GATE: nenhum dado interno
exposto indevidamente.

Conteúdo `interno` (canal, mensagem, documento, tarefa, reunião,
stakeholder) é só da empresa que o criou; o comprador nunca vê o negócio do
CRM do vendedor; participantes restringem usuários; leitor não escreve.
"""

from datetime import UTC, datetime, timedelta

VENDEDOR = "tenant-teste"
COMPRADOR = "tenant-comprador-sala"
R = "/api/v1/rede-social"


def _sala(client, criar_usuario_autenticado):
    comprador = criar_usuario_autenticado(COMPRADOR, papel="admin", email="admin@comprador-sala.com")
    conexao = client.post(f"{R}/conexoes", json={"tenant_id_destino": COMPRADOR}).json()
    client.put(f"{R}/conexoes/{conexao['id']}", json={"aceitar": True}, headers=comprador)
    sala = client.post(f"{R}/salas", json={"tenant_id_alvo": COMPRADOR}).json()
    return sala["id"], comprador


def _texto(resposta) -> str:
    assert resposta.status_code == 200, resposta.text
    return resposta.text


def test_conteudo_interno_do_vendedor_nunca_aparece_para_o_comprador(client, criar_usuario_autenticado):
    sala_id, comprador = _sala(client, criar_usuario_autenticado)
    canal_interno = client.post(f"{R}/salas/{sala_id}/canais", json={"tipo": "CUSTOM", "nome": "estrategia", "escopo": "interno"}).json()
    client.post(f"{R}/salas/canais/{canal_interno['id']}/mensagens", json={"texto": "Margem mínima 12%, desconto até 8%"})
    doc_canal = client.post(f"{R}/salas/{sala_id}/documentos", data={"canal_id": str(canal_interno["id"])},
                            files={"arquivo": ("precos.txt", b"tabela interna de precos", "text/plain")}).json()
    doc_interno = client.post(f"{R}/salas/{sala_id}/documentos", data={"escopo": "interno"},
                              files={"arquivo": ("plano.txt", b"plano de conta", "text/plain")}).json()
    client.post(f"{R}/salas/{sala_id}/documentos", files={"arquivo": ("proposta.txt", b"proposta comercial", "text/plain")})
    client.post(f"{R}/salas/{sala_id}/tarefas", json={"titulo": "Aprovar desconto com diretoria", "escopo": "interno"})
    client.post(f"{R}/salas/{sala_id}/tarefas", json={"titulo": "Enviar proposta", "responsavel_tenant_id": VENDEDOR})
    client.post(f"{R}/salas/{sala_id}/reunioes", json={"titulo": "Preparação interna",
                                                       "inicio": (datetime.now(UTC) + timedelta(days=1)).isoformat(), "escopo": "interno"})
    client.post(f"{R}/salas/{sala_id}/reunioes", json={"titulo": "Demonstração", "inicio": (datetime.now(UTC) + timedelta(days=2)).isoformat()})
    client.post(f"{R}/salas/{sala_id}/stakeholders", json={"nome": "Carlos", "lado": "COMPRADOR", "papel": "BLOCKER",
                                                           "notas": "resiste à troca de fornecedor"})
    client.post(f"{R}/salas/{sala_id}/stakeholders", json={"nome": "Ana", "lado": "VENDEDOR", "papel": "CHAMPION",
                                                           "escopo": "compartilhado", "notas": "nota privada da Ana"})

    visto = client.get(f"{R}/salas/{sala_id}/workspace", headers=comprador).json()
    texto = _texto(client.get(f"{R}/salas/{sala_id}/workspace", headers=comprador))
    for segredo in ("estrategia", "Margem", "precos.txt", "plano.txt", "Aprovar desconto", "Preparação interna", "BLOCKER",
                    "Carlos", "resiste", "nota privada"):
        assert segredo not in texto, segredo
    assert [d["nome_arquivo"] for d in visto["documentos"]] == ["proposta.txt"]
    assert [t["titulo"] for t in visto["tarefas"]] == ["Enviar proposta"] and visto["tarefas"][0]["responsavel"] == "ELES"
    assert [r["titulo"] for r in visto["reunioes"]] == ["Demonstração"]
    assert [(s["nome"], s["papel"], s["notas"]) for s in visto["stakeholders"]] == [("Ana", "CHAMPION", None)]

    for doc in (doc_canal, doc_interno):
        assert client.get(f"{R}/salas/documentos/{doc['id']}/arquivo", headers=comprador).status_code == 404
    assert client.get(f"{R}/salas/canais/{canal_interno['id']}/mensagens", headers=comprador).status_code == 404
    assert doc_canal["escopo"] == "interno"  # herda a fronteira do canal

    proprio = client.get(f"{R}/salas/{sala_id}/workspace").json()
    assert len(proprio["documentos"]) == 3 and len(proprio["stakeholders"]) == 2
    assert next(s for s in proprio["stakeholders"] if s["nome"] == "Carlos")["notas"] == "resiste à troca de fornecedor"


def test_comprador_nunca_ve_o_negocio_do_crm_do_vendedor(client, criar_usuario_autenticado, db_session):
    sala_id, comprador = _sala(client, criar_usuario_autenticado)
    conta = client.post("/api/v1/leads/contas", json={"nome": "Comprador SA"}).json()
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": "Carlos"}).json()
    negocio = client.post("/api/v1/crm/negocios", json={"conta_id": conta["id"], "decisor_id": decisor["id"],
                                                        "nome": "Upsell agressivo - margem 40%", "valor": 987654}).json()
    client.post(f"{R}/salas/{sala_id}/negocio", json={"negocio_id": negocio["id"], "visivel_para_comprador": True})
    client.put(f"{R}/salas/{sala_id}/negocio/compartilhado", json={"titulo_compartilhado": "Projeto de modernização",
                                                                     "fase_compartilhada": "PROPOSTA"})

    for path in (f"/salas/{sala_id}/negocio", f"/salas/{sala_id}/workspace"):
        texto = _texto(client.get(R + path, headers=comprador))
        assert "Upsell" not in texto and "987654" not in texto and "Descoberta" not in texto, path
    visto = client.get(f"{R}/salas/{sala_id}/workspace", headers=comprador).json()["sala_de_compra"]
    assert visto == {"e_vendedor": False, "titulo_compartilhado": "Projeto de modernização", "fase_compartilhada": "PROPOSTA"}
    do_vendedor = client.get(f"{R}/salas/{sala_id}/workspace").json()["sala_de_compra"]
    assert do_vendedor["negocio_nome"] == "Upsell agressivo - margem 40%" and do_vendedor["estagio_interno"] == "Descoberta"
    assert client.put(f"{R}/salas/{sala_id}/negocio/compartilhado", json={"fase_compartilhada": "GANHO"}).status_code == 422
    assert client.put(f"{R}/salas/{sala_id}/negocio/compartilhado", json={"titulo_compartilhado": "Tentativa do comprador"}, headers=comprador).status_code == 404


def test_participantes_restringem_usuarios_e_leitor_nao_escreve(client, criar_usuario_autenticado, db_session):
    from app.models.usuario import Usuario

    sala_id, comprador = _sala(client, criar_usuario_autenticado)
    leitor = criar_usuario_autenticado(VENDEDOR, papel="user", email="leitor@vendedor.com")
    fora = criar_usuario_autenticado(VENDEDOR, papel="user", email="fora@vendedor.com")
    leitor_id = db_session.query(Usuario).filter_by(email="leitor@vendedor.com").one().id
    comprador_id = db_session.query(Usuario).filter_by(email="admin@comprador-sala.com").one().id

    assert client.put(f"{R}/salas/{sala_id}/participantes", json=[{"usuario_id": comprador_id}]).status_code == 422
    assert client.put(f"{R}/salas/{sala_id}/participantes", json=[{"usuario_id": leitor_id, "papel": "LEITOR"}], headers=leitor).status_code == 403
    assert client.put(f"{R}/salas/{sala_id}/participantes", json=[{"usuario_id": leitor_id, "papel": "LEITOR"}]).status_code == 200

    assert client.get(f"{R}/salas/{sala_id}/workspace", headers=fora).status_code == 403
    assert client.get(f"{R}/salas/{sala_id}/canais", headers=fora).status_code == 403
    assert client.get(f"{R}/salas/{sala_id}/workspace", headers=leitor).status_code == 200
    canal = client.get(f"{R}/salas/{sala_id}/canais", headers=leitor).json()[0]
    assert client.post(f"{R}/salas/canais/{canal['id']}/mensagens", json={"texto": "oi"}, headers=leitor).status_code == 403
    assert client.post(f"{R}/salas/{sala_id}/tarefas", json={"titulo": "Tarefa do leitor"}, headers=leitor).status_code == 403
    # o comprador não vê quem participa pelo vendedor, e o lado dele continua aberto
    assert client.get(f"{R}/salas/{sala_id}/participantes", headers=comprador).json() == []
    assert client.post(f"{R}/salas/canais/{canal['id']}/mensagens", json={"texto": "olá"}, headers=comprador).status_code == 201


def test_tarefa_interna_nao_atribui_a_outra_empresa_e_empresa_de_fora_nao_entra(client, criar_usuario_autenticado):
    sala_id, comprador = _sala(client, criar_usuario_autenticado)
    assert client.post(f"{R}/salas/{sala_id}/tarefas", json={"titulo": "Tarefa interna", "escopo": "interno",
                                                             "responsavel_tenant_id": COMPRADOR}).status_code == 422
    assert client.post(f"{R}/salas/{sala_id}/tarefas", json={"titulo": "Tarefa de fora", "responsavel_tenant_id": "outra"}).status_code == 422
    tarefa = client.post(f"{R}/salas/{sala_id}/tarefas", json={"titulo": "Plano interno", "escopo": "interno"}).json()
    assert client.patch(f"{R}/salas/tarefas/{tarefa['id']}", json={"status": "CONCLUIDA"}, headers=comprador).status_code == 404

    terceiro = criar_usuario_autenticado("tenant-terceiro-sala", papel="admin", email="admin@terceiro-sala.com")
    for path in (f"/salas/{sala_id}/workspace", f"/salas/{sala_id}/canais", f"/salas/{sala_id}/negocio"):
        assert client.get(R + path, headers=terceiro).status_code == 403, path
    assert client.post(f"{R}/salas/{sala_id}/documentos", files={"arquivo": ("a.txt", b"x", "text/plain")}, headers=terceiro).status_code == 403
