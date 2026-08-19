from datetime import UTC, datetime

from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service

TENANT_ID = "tenant-teste"


def _criar_admin_hierarquico(db_session, tenant_id: str, tipo: str, tenant_pai_id: str | None = None) -> dict[str, str]:
    """Cria um tenant com hierarquia + seu admin, direto no banco (não via
    rota) — pensado pros testes de hierarquia, que precisam controlar
    `tipo`/`tenant_pai_id`, algo que `criar_usuario_autenticado` não expõe."""
    plano_id = _criar_plano(db_session, nome=f"Plano {tenant_id}", franquia=500)
    db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo, tenant_pai_id=tenant_pai_id))
    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano_id, status="ativa"))
    db_session.flush()
    usuario = Usuario(
        tenant_id=tenant_id, nome=f"Admin {tenant_id}", email=f"admin@{tenant_id}.com.br", papel="admin", ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    token = auth_service.gerar_token(usuario)
    return {"Authorization": f"Bearer {token}"}


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
    # Raio-X (hierarquia de distribuidores): o primeiro usuário de um tenant
    # criado via HTTP agora sempre nasce "admin", nunca mais "super_admin"
    # — senão qualquer Distribuidor/Revendedor mintaria acesso cross-*toda*
    # a plataforma ao criar um tenant novo. "super_admin" de verdade só
    # nasce por scripts/bootstrap_tenant.py (ovo-e-galinha da CyberFort).
    assert resposta.json()["usuario"]["papel"] == "admin"


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


def test_atribuir_primeira_licenca_a_tenant_sem_licenca(client, db_session):
    """Bug reportado: tenant nascido via convite-vitrine (Onda H) não tem
    nenhuma `Licenca` — a tela de Admin precisa conseguir criar a
    primeira, não só editar uma que já existe."""
    plano_id = _criar_plano(db_session, nome="Vitrine-Upgrade", franquia=200)
    db_session.add(Tenant(id="tenant-vitrine", razao_social="Empresa Vitrine"))
    db_session.commit()

    resposta_antes = client.get("/api/v1/admin/tenants/tenant-vitrine/licenca")
    assert resposta_antes.status_code == 404

    resposta = client.put(
        "/api/v1/admin/tenants/tenant-vitrine/licenca", json={"plano_id": plano_id, "status": "ativa"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["plano_id"] == plano_id
    assert corpo["status"] == "ativa"

    resposta_depois = client.get("/api/v1/admin/tenants/tenant-vitrine/licenca")
    assert resposta_depois.status_code == 200


def test_criar_primeira_licenca_exige_plano(client, db_session):
    db_session.add(Tenant(id="tenant-sem-plano", razao_social="Empresa Sem Plano"))
    db_session.commit()

    resposta = client.put("/api/v1/admin/tenants/tenant-sem-plano/licenca", json={"status": "ativa"})

    assert resposta.status_code == 409


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


# --- Hierarquia de tenants (raio-X: fundação da API de provisionamento) ---


def test_distribuidor_cria_revendedor_que_cria_cliente(client, db_session):
    plano_id = _criar_plano(db_session, nome="Revenda", franquia=200)
    headers_distribuidor = _criar_admin_hierarquico(db_session, "distribuidora-x", tipo="distribuidor")

    resposta_revendedor = client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "revenda-x1",
            "razao_social": "Revenda X1",
            "plano_id": plano_id,
            "nome_admin": "Admin Revenda",
            "email_admin": "admin@revendax1.com.br",
            "senha_admin": "senha123",
            "tenant_pai_id": "distribuidora-x",
            "tipo": "revendedor",
        },
        headers=headers_distribuidor,
    )
    assert resposta_revendedor.status_code == 201
    assert resposta_revendedor.json()["tipo"] == "revendedor"
    assert resposta_revendedor.json()["tenant_pai_id"] == "distribuidora-x"

    login_revendedor = client.post(
        "/api/v1/auth/login", json={"email": "admin@revendax1.com.br", "senha": "senha123"}
    )
    headers_revendedor = {"Authorization": f"Bearer {login_revendedor.json()['access_token']}"}
    assert login_revendedor.json()["usuario"]["papel"] == "admin"
    assert login_revendedor.json()["usuario"]["tenant_tipo"] == "revendedor"

    resposta_cliente = client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "cliente-x1a",
            "razao_social": "Cliente X1A",
            "plano_id": plano_id,
            "nome_admin": "Admin Cliente",
            "email_admin": "admin@clientex1a.com.br",
            "senha_admin": "senha123",
            "tenant_pai_id": "revenda-x1",
            "tipo": "cliente",
        },
        headers=headers_revendedor,
    )
    assert resposta_cliente.status_code == 201

    # Distribuidor enxerga a árvore inteira (si mesmo + revendedor + cliente).
    tenants_do_distribuidor = client.get("/api/v1/admin/tenants", headers=headers_distribuidor).json()
    assert {t["id"] for t in tenants_do_distribuidor} == {"distribuidora-x", "revenda-x1", "cliente-x1a"}


def test_revendedor_nao_consegue_criar_tenant_fora_do_proprio(client, db_session):
    _criar_plano(db_session, nome="Fora", franquia=200)
    plano_id = _criar_plano(db_session, nome="Fora2", franquia=200)
    headers_revendedor_a = _criar_admin_hierarquico(db_session, "revenda-y1", tipo="revendedor")

    resposta = client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": "cliente-invasor",
            "razao_social": "Invasor",
            "plano_id": plano_id,
            "nome_admin": "X",
            "email_admin": "invasor@x.com.br",
            "senha_admin": "senha123",
            "tenant_pai_id": "outro-tenant-que-nao-e-o-meu",
            "tipo": "cliente",
        },
        headers=headers_revendedor_a,
    )

    assert resposta.status_code == 403


def test_revendedor_nao_ve_licenca_de_tenant_fora_da_propria_arvore(client, db_session):
    headers_revendedor_a = _criar_admin_hierarquico(db_session, "revenda-z1", tipo="revendedor")
    _criar_admin_hierarquico(db_session, "revenda-z2", tipo="revendedor")  # árvore irmã

    resposta = client.get("/api/v1/admin/tenants/revenda-z2/licenca", headers=headers_revendedor_a)

    assert resposta.status_code == 403


def test_revendedor_ve_licenca_do_proprio_cliente(client, db_session):
    headers_revendedor = _criar_admin_hierarquico(db_session, "revenda-w1", tipo="revendedor")
    _criar_admin_hierarquico(db_session, "cliente-w1a", tipo="cliente", tenant_pai_id="revenda-w1")

    resposta = client.get("/api/v1/admin/tenants/cliente-w1a/licenca", headers=headers_revendedor)

    assert resposta.status_code == 200


def test_admin_de_cliente_comum_nao_acessa_admin_tenants(client, db_session):
    """Admin de um tenant tipo="cliente" (o caso de toda conta comum de
    hoje) continua sem acesso a /admin/tenants — só distribuidor/revendedor
    e super_admin ganham a visão hierárquica."""
    headers_cliente = _criar_admin_hierarquico(db_session, "cliente-comum-w", tipo="cliente")

    resposta = client.get("/api/v1/admin/tenants", headers=headers_cliente)

    assert resposta.status_code == 403


def test_licenca_consolidada_herda_status_do_tenant_pai(client, db_session, criar_usuario_autenticado):
    """raio-X: modo_cobranca="consolidada" — o cliente não tem cobrança
    própria, o status de pagamento vem do tenant pai."""
    plano_id = _criar_plano(db_session, nome="Consolidado", franquia=200)
    db_session.add(Tenant(id="pai-pagante", razao_social="Pai Pagante"))
    db_session.add(Licenca(tenant_id="pai-pagante", plano_id=plano_id, status="ativa"))
    db_session.add(
        Tenant(id="filho-consolidado", razao_social="Filho Consolidado", tenant_pai_id="pai-pagante", modo_cobranca="consolidada")
    )
    # Filho tem sua própria licença (limites/plano), mas com status que
    # SERIA recusado se fosse checado isoladamente — a consolidação deve
    # ignorar esse status e olhar pro pai.
    db_session.add(Licenca(tenant_id="filho-consolidado", plano_id=plano_id, status="suspensa"))
    db_session.commit()

    headers_filho = criar_usuario_autenticado("filho-consolidado", papel="user")

    resposta = client.get("/api/v1/icp", headers=headers_filho)

    assert resposta.status_code == 200


def test_cron_suspende_licencas_vencidas(client, db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "cron_secret", "segredo-teste-licenca")
    plano_id = _criar_plano(db_session, nome="Vencido", franquia=200)
    db_session.add(Tenant(id="tenant-vencido-cron", razao_social="Vencido"))
    db_session.add(
        Licenca(
            tenant_id="tenant-vencido-cron", plano_id=plano_id, status="ativa",
            data_expiracao=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    db_session.commit()

    resposta = client.post(
        "/api/v1/cron/suspender-licencas-vencidas", headers={"X-Cron-Secret": "segredo-teste-licenca"}
    )

    assert resposta.status_code == 200
    assert "tenant-vencido-cron" in resposta.json()["tenants_suspensos"]
    assert db_session.query(Licenca).filter_by(tenant_id="tenant-vencido-cron").one().status == "suspensa"
