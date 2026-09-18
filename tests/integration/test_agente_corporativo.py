from app.models.oferta import Oferta
from app.models.usuario import Usuario
from app.services import auth_service

TENANT_B = "tenant-outro"
TENANT_SEM_LICENCA = "tenant-sem-licenca"


def _conectar_e_aceitar(client, headers_b):
    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_b)


def test_definir_e_obter_modo(client):
    resposta = client.put("/api/v1/agente-corporativo/modo", json={"modo": "assistido"})
    assert resposta.status_code == 200
    assert resposta.json()["modo"] == "assistido"

    resposta = client.get("/api/v1/agente-corporativo/modo")
    assert resposta.json()["modo"] == "assistido"


def test_testar_agente_sem_ativar_retorna_erro(client):
    resposta = client.post("/api/v1/agente-corporativo/testar", json={"pergunta": "qualquer coisa"})
    assert resposta.status_code == 409


def test_fluxo_perguntar_aprovar_via_api(client, criar_usuario_autenticado, db_session):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _conectar_e_aceitar(client, headers_b)

    client.put("/api/v1/agente-corporativo/modo", json={"modo": "assistido"}, headers=headers_b)
    db_session.add(Oferta(tenant_id=TENANT_B, nome="Backup Imutável", descricao="Solução de backup em nuvem", ativo=True))
    db_session.commit()

    resposta = client.post(
        "/api/v1/agente-corporativo/perguntar", json={"tenant_id_alvo": TENANT_B, "pergunta": "vocês tem backup?"}
    )
    assert resposta.status_code == 201
    pergunta_id = resposta.json()["id"]
    assert resposta.json()["status"] == "pendente_aprovacao"

    pendentes = client.get("/api/v1/agente-corporativo/pendentes", headers=headers_b).json()
    assert len(pendentes) == 1

    aprovada = client.post(
        f"/api/v1/agente-corporativo/pendentes/{pergunta_id}/aprovar", json={}, headers=headers_b
    ).json()
    assert aprovada["status"] == "aprovada"

    minhas = client.get("/api/v1/agente-corporativo/minhas-perguntas").json()
    assert minhas[0]["resposta_final"] is not None


def test_perguntar_sem_conexao_retorna_erro(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.put("/api/v1/agente-corporativo/modo", json={"modo": "assistido"}, headers=headers_b)

    resposta = client.post(
        "/api/v1/agente-corporativo/perguntar", json={"tenant_id_alvo": TENANT_B, "pergunta": "vocês tem backup?"}
    )
    assert resposta.status_code == 409


def test_agente_corporativo_exige_licenca(client, db_session):
    usuario = Usuario(
        tenant_id=TENANT_SEM_LICENCA, nome="Sem Licença", email="admin@semlicenca.com.br", papel="admin", ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    headers_sem_licenca = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}

    resposta = client.get("/api/v1/agente-corporativo/modo", headers=headers_sem_licenca)

    assert resposta.status_code == 403
