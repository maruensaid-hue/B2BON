from app.models.plano import Plano

TENANT_ID = "tenant-teste"


def _criar_plano(db_session, nome: str = "Starter", franquia: int = 200) -> int:
    plano = Plano(nome=nome, franquia_contas_mes=franquia, max_usuarios=10, preco_mensal=490.0)
    db_session.add(plano)
    db_session.commit()
    return plano.id


def test_lista_planos_e_publica(client, db_session):
    _criar_plano(db_session)

    resposta = client.get("/api/v1/planos", headers={"Authorization": ""})

    assert resposta.status_code == 200
    assert len(resposta.json()) >= 1


def test_super_admin_cria_novo_tenant(client, db_session):
    """E8-H3-like (Onda A): onboarding de um novo tenant pelo super_admin já autenticado."""
    plano_id = _criar_plano(db_session, nome="Enterprise", franquia=5000)

    resposta = client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "novo-tenant",
            "razao_social": "Nova Empresa Ltda",
            "plano_id": plano_id,
            "nome_admin": "Admin Novo",
            "email_admin": "admin@novoempresa.com.br",
            "senha_admin": "senha123",
        },
    )

    assert resposta.status_code == 201
    assert resposta.json()["id"] == "novo-tenant"

    tenants = client.get("/api/v1/admin/tenants").json()
    assert any(t["id"] == "novo-tenant" for t in tenants)


def test_novo_admin_de_tenant_consegue_logar(client, db_session):
    plano_id = _criar_plano(db_session, nome="Starter2", franquia=200)
    client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "empresa-login",
            "razao_social": "Empresa Login",
            "plano_id": plano_id,
            "nome_admin": "Admin Login",
            "email_admin": "admin@empresalogin.com.br",
            "senha_admin": "senha123",
        },
    )

    resposta = client.post(
        "/api/v1/auth/login", json={"email": "admin@empresalogin.com.br", "senha": "senha123"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["usuario"]["tenant_id"] == "empresa-login"
    assert resposta.json()["usuario"]["papel"] == "super_admin"


def test_atualizar_licenca_do_tenant(client, db_session):
    plano_a_id = _criar_plano(db_session, nome="StarterX", franquia=200)
    plano_b_id = _criar_plano(db_session, nome="ProfessionalX", franquia=800)
    client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "empresa-x",
            "razao_social": "Empresa X",
            "plano_id": plano_a_id,
            "nome_admin": "Admin X",
            "email_admin": "admin@empresax.com.br",
            "senha_admin": "senha123",
        },
    )

    resposta = client.put(
        "/api/v1/admin/tenants/empresa-x/licenca", json={"plano_id": plano_b_id, "status": "ativa"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["plano_id"] == plano_b_id


def test_criar_tenant_bloqueado_para_nao_super_admin(client, criar_usuario_autenticado, db_session):
    plano_id = _criar_plano(db_session, nome="Bloqueado", franquia=200)
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-comum@teste.com.br")

    resposta = client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "tentativa-bloqueada",
            "razao_social": "X",
            "plano_id": plano_id,
            "nome_admin": "X",
            "email_admin": "x@x.com.br",
            "senha_admin": "senha123",
        },
        headers=headers_admin,
    )

    assert resposta.status_code == 403
