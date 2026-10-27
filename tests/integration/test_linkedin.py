_CSV_EXPORT_LINKEDIN = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are blank."


First Name,Last Name,URL,Email Address,Company,Position,Connected On
Joao,Silva,https://www.linkedin.com/in/joao-silva,joao@example.com,Alpha Tech,CEO,01 Jan 2024
Maria,Souza,https://www.linkedin.com/in/maria-souza/,,Beta Clinica,Diretora,15 Mar 2023
"""

# Raio-X 2026-09-15: só 1 toque de WhatsApp por cadência.
_TOQUES_LINKEDIN_PRIMEIRO = [
    {"ordem": 1, "canal": "linkedin", "intervalo_dias_apos_anterior": 0},
    {"ordem": 2, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 2},
    {"ordem": 4, "canal": "whatsapp", "intervalo_dias_apos_anterior": 2, "template_whatsapp_id": "x"},
    {"ordem": 5, "canal": "email", "intervalo_dias_apos_anterior": 2},
]


def _criar_gerar_aprovar_ativar(client, conta_id: int, toques: list[dict]) -> dict:
    cadencia = client.post("/api/v1/cadencias", json={"nome": "Cadência LinkedIn", "toques": toques}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta_id]})
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    for item in itens:
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    return cadencia


def test_tarefa_linkedin_tem_texto_e_link(client, onboarding_completo, criar_conta_com_decisor):
    """E3-H4: tarefa diária de LinkedIn com texto copiável e atalho para o perfil."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)

    client.post("/api/v1/envios/processar")
    tarefas = client.get("/api/v1/linkedin/tarefas").json()

    assert len(tarefas) == 1
    assert tarefas[0]["texto"]
    assert tarefas[0]["link_perfil"] == decisor.linkedin_url
    assert tarefas[0]["status"] == "pendente"


def test_linkedin_nunca_envia_automaticamente(
    client, onboarding_completo, criar_conta_com_decisor, fake_whatsapp, fake_email
):
    """E3-H4: nenhum envio automatizado ao LinkedIn em nenhuma hipótese."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["tarefas_linkedin_criadas"] == 1
    assert resultado["enviadas"] == 0
    assert fake_whatsapp.envios == []
    assert fake_email.envios == []


def test_marcar_executada_realimenta_cadencia(client, onboarding_completo, criar_conta_com_decisor):
    """E3-H4: marcação de executado realimenta a cadência."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)
    client.post("/api/v1/envios/processar")
    tarefa = client.get("/api/v1/linkedin/tarefas").json()[0]

    resposta = client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": True})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "executada"


def test_marcar_ignorada_cancela_mensagem(client, onboarding_completo, criar_conta_com_decisor):
    """E3-H4: marcação de ignorado também realimenta a cadência."""
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)
    client.post("/api/v1/envios/processar")
    tarefa = client.get("/api/v1/linkedin/tarefas").json()[0]

    resposta = client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": False})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ignorada"


def test_importar_conexoes_reconhece_export_oficial_do_linkedin(client):
    """O export real do LinkedIn traz linhas de nota antes do cabeçalho —
    o parser precisa achar a linha certa mesmo assim."""
    resposta = client.post("/api/v1/linkedin/conexoes/importar", json={"conteudo_csv": _CSV_EXPORT_LINKEDIN})

    assert resposta.status_code == 200
    assert resposta.json()["total_importado"] == 2

    status = client.get("/api/v1/linkedin/conexoes/status").json()
    assert status["total"] == 2
    assert status["atualizado_em"] is not None


def test_importar_conexoes_csv_invalido_retorna_erro_claro(client):
    resposta = client.post("/api/v1/linkedin/conexoes/importar", json={"conteudo_csv": "nao,e,um,csv,do,linkedin"})

    assert resposta.status_code == 422
    assert "conexões do LinkedIn" in resposta.json()["detalhe"]


def test_reupload_substitui_em_vez_de_acumular(client):
    client.post("/api/v1/linkedin/conexoes/importar", json={"conteudo_csv": _CSV_EXPORT_LINKEDIN})
    client.post("/api/v1/linkedin/conexoes/importar", json={"conteudo_csv": _CSV_EXPORT_LINKEDIN})

    status = client.get("/api/v1/linkedin/conexoes/status").json()
    assert status["total"] == 2


def test_status_sem_importacao_retorna_zero(client):
    status = client.get("/api/v1/linkedin/conexoes/status").json()

    assert status == {"total": 0, "atualizado_em": None}


def test_importar_conexoes_pela_api_cria_contatos_empresas_e_a_lista_importacao_linkedin(client, onboarding_completo):
    csv = _CSV_EXPORT_LINKEDIN + "Caio,Dias,https://www.linkedin.com/in/caio,caio@alpha.com,ALPHA TECH Ltda,CTO,02 Jan 2024\n"
    r = client.post("/api/v1/linkedin/conexoes/importar", json={"conteudo_csv": csv})
    assert r.status_code == 200
    d = r.json()
    assert (d["total_importado"], d["contas_criadas"], d["contatos_criados"], d["lista_nome"]) == (3, 2, 3, "Importação LinkedIn")
    listas = client.get("/api/v1/listas-prospeccao").json()
    assert [lista["nome"] for lista in listas if lista["id"] == d["lista_id"]] == ["Importação LinkedIn"]
    contas = client.get(f"/api/v1/listas-prospeccao/{d['lista_id']}/contas").json()
    assert sorted(c["nome"] for c in contas) == ["Alpha Tech", "Beta Clinica"]
    contatos = {c["nome"]: c for c in client.get("/api/v1/leads/decisores").json()}  # a lista de contatos traz o perfil do LinkedIn de cada conexão
    assert contatos["Joao Silva"]["linkedin_url"] == "https://linkedin.com/in/joao-silva" and contatos["Joao Silva"]["cargo"] == "CEO"
    assert contatos["Caio Dias"]["email"] == "caio@alpha.com"
    assert client.post("/api/v1/linkedin/conexoes/importar", json={"conteudo_csv": csv}).json()["contatos_criados"] == 0  # idempotente


def _tarefa_pendente(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    _criar_gerar_aprovar_ativar(client, conta.id, _TOQUES_LINKEDIN_PRIMEIRO)
    client.post("/api/v1/envios/processar")
    return conta, decisor, client.get("/api/v1/linkedin/tarefas").json()[0]


def test_tarefa_traz_o_contato_e_a_empresa_para_a_tela(client, onboarding_completo, criar_conta_com_decisor):
    conta, decisor, tarefa = _tarefa_pendente(client, criar_conta_com_decisor)

    assert tarefa["decisor_nome"] == decisor.nome
    assert tarefa["conta_id"] == conta.id and tarefa["conta_nome"] == (conta.nome_fantasia or conta.nome)


def test_contagem_do_menu_cai_quando_a_tarefa_e_marcada(client, onboarding_completo, criar_conta_com_decisor):
    _, _, tarefa = _tarefa_pendente(client, criar_conta_com_decisor)
    assert client.get("/api/v1/linkedin/tarefas/contagem").json() == {"pendentes": 1}

    client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": True})

    assert client.get("/api/v1/linkedin/tarefas/contagem").json() == {"pendentes": 0}
    assert client.get("/api/v1/linkedin/tarefas", params={"status": "pendente"}).json() == []
    assert [t["status"] for t in client.get("/api/v1/linkedin/tarefas", params={"status": "executada"}).json()] == ["executada"]


def test_marcar_enviada_atualiza_a_mensagem_e_a_linha_do_tempo_da_conta(client, onboarding_completo, criar_conta_com_decisor, db_session):
    from app.models.atividade import Atividade
    from app.models.mensagem import Mensagem

    conta, decisor, tarefa = _tarefa_pendente(client, criar_conta_com_decisor)

    client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": True})

    db_session.expire_all()
    mensagem = db_session.get(Mensagem, tarefa["mensagem_id"])
    assert mensagem.status == "enviado" and mensagem.enviado_em is not None
    atividades = db_session.query(Atividade).filter_by(conta_id=conta.id, tipo="linkedin").all()
    assert len(atividades) == 1 and decisor.nome in atividades[0].descricao


def test_marcar_a_mesma_tarefa_de_novo_nao_duplica_e_a_marcacao_contraria_e_recusada(
    client, onboarding_completo, criar_conta_com_decisor, db_session
):
    from app.models.atividade import Atividade

    conta, _, tarefa = _tarefa_pendente(client, criar_conta_com_decisor)
    url = f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar"

    assert client.post(url, json={"executada": True}).status_code == 200
    repetida = client.post(url, json={"executada": True})  # duplo clique

    assert repetida.status_code == 200 and repetida.json()["status"] == "executada"
    assert db_session.query(Atividade).filter_by(conta_id=conta.id, tipo="linkedin").count() == 1
    contraria = client.post(url, json={"executada": False})
    assert contraria.status_code in (409, 422) and "já foi marcada" in contraria.text


def test_tarefa_de_linkedin_de_outro_tenant_nao_aparece_nem_pode_ser_marcada(
    client, onboarding_completo, criar_conta_com_decisor, criar_usuario_autenticado
):
    _, _, tarefa = _tarefa_pendente(client, criar_conta_com_decisor)
    outro = criar_usuario_autenticado("outro-tenant-linkedin")

    assert client.get("/api/v1/linkedin/tarefas", headers=outro).json() == []
    assert client.get("/api/v1/linkedin/tarefas/contagem", headers=outro).json() == {"pendentes": 0}
    assert client.post(f"/api/v1/linkedin/tarefas/{tarefa['id']}/marcar", json={"executada": True}, headers=outro).status_code == 404
