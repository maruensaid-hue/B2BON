from app.models.conta import Conta
from app.models.usuario import Usuario
from app.services import auth_service

TENANT_B = "tenant-outro"
TENANT_SEM_LICENCA = "tenant-sem-licenca"


def _criar_icp(client) -> int:
    resposta = client.post(
        "/api/v1/icp",
        json={
            "nome": "Healthcare Enterprise",
            "segmento": "healthcare",
            "porte": "grande",
            "regiao": "sudeste",
            "cnae_codigos": ["8610-1/01"],
            "ufs": ["SP"],
        },
    )
    return resposta.json()["id"]


def test_gerar_e_listar_sinais_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _criar_icp(client)
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP"},
        headers=headers_b,
    )

    resposta_gerar = client.post("/api/v1/inteligencia-rede/sinais/gerar")
    assert resposta_gerar.status_code == 200
    sinais = resposta_gerar.json()
    assert len(sinais) == 1
    assert sinais[0]["tenant_id_alvo"] == TENANT_B

    resposta_listar = client.get("/api/v1/inteligencia-rede/sinais")
    assert resposta_listar.status_code == 200
    assert len(resposta_listar.json()) == 1


def test_marcar_visto_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _criar_icp(client)
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP"},
        headers=headers_b,
    )
    sinal = client.post("/api/v1/inteligencia-rede/sinais/gerar").json()[0]

    resposta = client.post(f"/api/v1/inteligencia-rede/sinais/{sinal['id']}/visto")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "visto"


def test_descartar_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _criar_icp(client)
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP"},
        headers=headers_b,
    )
    sinal = client.post("/api/v1/inteligencia-rede/sinais/gerar").json()[0]

    resposta = client.post(f"/api/v1/inteligencia-rede/sinais/{sinal['id']}/descartar")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "descartado"


def test_converter_via_api_cria_conta_no_crm(client, criar_usuario_autenticado, db_session):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _criar_icp(client)
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP"},
        headers=headers_b,
    )
    sinal = client.post("/api/v1/inteligencia-rede/sinais/gerar").json()[0]

    resposta = client.post(f"/api/v1/inteligencia-rede/sinais/{sinal['id']}/converter")

    assert resposta.status_code == 200
    conta_id = resposta.json()["conta_id"]
    conta = db_session.query(Conta).filter_by(id=conta_id).one()
    assert conta.origem == "rede_social_signal"

    sinal_convertido = client.get("/api/v1/inteligencia-rede/sinais").json()[0]
    assert sinal_convertido["status"] == "convertido"
    assert sinal_convertido["conta_id_gerada"] == conta_id


def test_converter_novamente_retorna_erro_de_negocio(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    _criar_icp(client)
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP"},
        headers=headers_b,
    )
    sinal = client.post("/api/v1/inteligencia-rede/sinais/gerar").json()[0]
    client.post(f"/api/v1/inteligencia-rede/sinais/{sinal['id']}/converter")

    resposta = client.post(f"/api/v1/inteligencia-rede/sinais/{sinal['id']}/converter")

    assert resposta.status_code == 409


def test_sinais_exige_licenca(client, db_session):
    usuario = Usuario(
        tenant_id=TENANT_SEM_LICENCA, nome="Sem Licença", email="admin@semlicenca2.com.br", papel="admin", ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    headers_sem_licenca = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}

    resposta = client.get("/api/v1/inteligencia-rede/sinais", headers=headers_sem_licenca)

    assert resposta.status_code == 403
