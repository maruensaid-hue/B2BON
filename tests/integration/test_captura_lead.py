from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.negocio import Negocio
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service, link_captura_lead_service

TENANT_ID = "tenant-captura-lead"


def _criar_tenant(db_session, tenant_id: str = TENANT_ID) -> Tenant:
    tenant = Tenant(id=tenant_id, razao_social="Empresa Dona do Link Ltda")
    db_session.add(tenant)
    db_session.commit()
    return tenant


def _criar_usuario_logado(db_session, client, tenant_id: str = TENANT_ID) -> dict:
    usuario = Usuario(
        tenant_id=tenant_id,
        nome="Admin",
        email=f"admin@{tenant_id}.com.br",
        senha_hash=auth_service.hash_senha("senha123"),
        papel="admin",
        ativo=True,
    )
    db_session.add(usuario)
    db_session.commit()
    resposta = client.post("/api/v1/auth/login", json={"email": usuario.email, "senha": "senha123"})
    token = resposta.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_obter_config_gera_link_na_primeira_vez(client, db_session):
    _criar_tenant(db_session)
    headers = _criar_usuario_logado(db_session, client)

    resposta = client.get("/api/v1/captura-lead/config", headers=headers)

    assert resposta.status_code == 200
    codigo = resposta.json()["codigo"]
    assert codigo

    resposta_2 = client.get("/api/v1/captura-lead/config", headers=headers)
    assert resposta_2.json()["codigo"] == codigo  # idempotente


def test_info_publica_por_codigo(client, db_session):
    _criar_tenant(db_session)
    link = link_captura_lead_service.obter_ou_criar(db_session, TENANT_ID)

    resposta = client.get(f"/api/v1/captura-lead/{link.codigo}/info")

    assert resposta.status_code == 200
    assert resposta.json()["nome_exibicao"] == TENANT_ID  # sem PerfilEmpresa cadastrado, cai no tenant_id


def test_info_publica_codigo_invalido_retorna_404(client):
    resposta = client.get("/api/v1/captura-lead/CODIGO-INEXISTENTE/info")

    assert resposta.status_code == 404


def test_submeter_lead_cria_conta_prospect_sem_negocio(client, db_session):
    _criar_tenant(db_session)
    link = link_captura_lead_service.obter_ou_criar(db_session, TENANT_ID)

    resposta = client.post(
        f"/api/v1/captura-lead/{link.codigo}",
        json={
            "nome_empresa": "Prospect Via Anúncio Ltda",
            "cnpj": "12.345.678/0001-90",
            "nome_contato": "Fulano de Tal",
            "email_contato": "fulano@prospect.com.br",
            "telefone_contato": "11999998888",
            "cargo_contato": "Diretor",
        },
    )

    assert resposta.status_code == 201
    conta = db_session.query(Conta).filter_by(tenant_id=TENANT_ID).one()
    assert conta.status == "prospectada"
    assert conta.icp_id is None
    assert conta.origem == "captura_lead_publica"
    decisor = db_session.query(Decisor).filter_by(conta_id=conta.id).one()
    assert decisor.nome == "Fulano de Tal"
    assert decisor.cargo == "Diretor"
    assert db_session.query(Negocio).filter_by(tenant_id=TENANT_ID).count() == 0


def test_submeter_lead_codigo_invalido_retorna_404(client):
    resposta = client.post(
        "/api/v1/captura-lead/CODIGO-INEXISTENTE",
        json={"nome_empresa": "X", "nome_contato": "Y", "email_contato": "y@x.com"},
    )

    assert resposta.status_code == 404


def test_submeter_lead_bloqueia_apos_muitas_tentativas(client, db_session):
    _criar_tenant(db_session)
    link = link_captura_lead_service.obter_ou_criar(db_session, TENANT_ID)
    payload = {"nome_empresa": "X", "nome_contato": "Y", "email_contato": "y@x.com"}

    for _ in range(3):
        resposta = client.post(f"/api/v1/captura-lead/{link.codigo}", json=payload)
        assert resposta.status_code == 201

    resposta = client.post(f"/api/v1/captura-lead/{link.codigo}", json=payload)

    assert resposta.status_code == 429


def test_leads_de_tenants_diferentes_nao_se_misturam(client, db_session):
    _criar_tenant(db_session, "tenant-a")
    _criar_tenant(db_session, "tenant-b")
    link_a = link_captura_lead_service.obter_ou_criar(db_session, "tenant-a")

    client.post(
        f"/api/v1/captura-lead/{link_a.codigo}",
        json={"nome_empresa": "Só do A", "nome_contato": "Y", "email_contato": "y@x.com"},
    )

    assert db_session.query(Conta).filter_by(tenant_id="tenant-a").count() == 1
    assert db_session.query(Conta).filter_by(tenant_id="tenant-b").count() == 0
