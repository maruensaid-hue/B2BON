from fastapi.testclient import TestClient

from app.main import app
from app.models.usuario import Usuario
from app.services import auth_service

TENANT_ID = "tenant-teste"


def _criar_usuario_senha(db_session, email: str, senha: str, papel: str = "user", tenant_id: str = TENANT_ID) -> Usuario:
    usuario = Usuario(
        tenant_id=tenant_id, nome="Fulano", email=email, senha_hash=auth_service.hash_senha(senha), papel=papel, ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_login_com_sucesso(client, db_session):
    _criar_usuario_senha(db_session, "login@teste.com.br", "senha-forte")

    resposta = client.post("/api/v1/auth/login", json={"email": "login@teste.com.br", "senha": "senha-forte"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["access_token"]
    assert corpo["token_type"] == "bearer"
    assert corpo["usuario"]["email"] == "login@teste.com.br"


def test_login_com_senha_errada_retorna_401(client, db_session):
    _criar_usuario_senha(db_session, "login2@teste.com.br", "senha-forte")

    resposta = client.post("/api/v1/auth/login", json={"email": "login2@teste.com.br", "senha": "errada"})

    assert resposta.status_code == 401


def test_login_com_email_inexistente_retorna_401(client):
    resposta = client.post("/api/v1/auth/login", json={"email": "ninguem@teste.com.br", "senha": "qualquer"})

    assert resposta.status_code == 401


def test_eu_retorna_usuario_autenticado(client):
    resposta = client.get("/api/v1/auth/eu")

    assert resposta.status_code == 200
    assert resposta.json()["tenant_id"] == TENANT_ID


def test_registrar_via_convite_gera_token_valido(client, db_session):
    """E11-ish do núcleo (Onda A): registro por convite retorna token utilizável."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    resposta = client.post(
        "/api/v1/auth/registrar",
        json={
            "codigo_convite": convite.codigo,
            "nome": "Novo",
            "email": "novo-via-api@teste.com.br",
            "senha": "senha123",
            "aceite_termos": True,
        },
    )

    assert resposta.status_code == 201
    token = resposta.json()["access_token"]

    eu = client.get("/api/v1/auth/eu", headers={"Authorization": f"Bearer {token}"})
    assert eu.status_code == 200
    assert eu.json()["email"] == "novo-via-api@teste.com.br"


def test_registrar_sem_aceitar_termos_via_api_falha(client, db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    resposta = client.post(
        "/api/v1/auth/registrar",
        json={
            "codigo_convite": convite.codigo,
            "nome": "Sem Aceite",
            "email": "sem-aceite-api@teste.com.br",
            "senha": "senha123",
            "aceite_termos": False,
        },
    )

    assert resposta.status_code == 422


def test_registrar_grava_data_do_aceite_dos_termos(client, db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    resposta = client.post(
        "/api/v1/auth/registrar",
        json={
            "codigo_convite": convite.codigo,
            "nome": "Com Aceite",
            "email": "com-aceite-api@teste.com.br",
            "senha": "senha123",
            "aceite_termos": True,
        },
    )

    assert resposta.status_code == 201
    assert resposta.json()["usuario"]["termos_aceitos_em"] is not None


def test_registrar_vitrine_sem_aceitar_termos_via_api_falha(client):
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Sem Aceite Vitrine Ltda",
            "nome_admin": "Admin",
            "email_admin": "sem-aceite-vitrine@teste.com.br",
            "senha_admin": "senha123",
            "aceite_termos": False,
        },
    )

    assert resposta.status_code == 422


def test_convite_usado_duas_vezes_falha(client, db_session):
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)
    client.post(
        "/api/v1/auth/registrar",
        json={
            "codigo_convite": convite.codigo,
            "nome": "A",
            "email": "a@teste.com.br",
            "senha": "senha123",
            "aceite_termos": True,
        },
    )

    resposta = client.post(
        "/api/v1/auth/registrar",
        json={
            "codigo_convite": convite.codigo,
            "nome": "B",
            "email": "b@teste.com.br",
            "senha": "senha123",
            "aceite_termos": True,
        },
    )

    assert resposta.status_code == 409


def test_endpoint_existente_exige_token_valido(client):
    """Prova que a blindagem de autenticação está ligada em rotas antigas do PREDATOR, não só nas novas."""
    resposta = client.get("/api/v1/contas/franquia", headers={"Authorization": "Bearer token-invalido"})

    assert resposta.status_code == 401


def test_endpoint_sem_header_authorization_retorna_401(client):
    """Ausência completa do header cai em 401 — não em 422, que seria o
    comportamento padrão do FastAPI para um Header(...) obrigatório
    faltante (misturaria "não autenticado" com "parâmetro inválido")."""
    cliente_sem_header = TestClient(app)

    resposta = cliente_sem_header.get("/api/v1/contas/franquia")

    assert resposta.status_code == 401


def test_rota_super_admin_bloqueada_para_usuario_comum(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="comum@teste.com.br")

    resposta = client.get("/api/v1/admin/tenants", headers=headers_user)

    assert resposta.status_code == 403


def test_gerar_e_listar_convite_via_api(client):
    resposta = client.post("/api/v1/convites", json={"papel_concedido": "user", "validade_horas": 24})
    assert resposta.status_code == 201
    codigo = resposta.json()["codigo"]

    listagem = client.get("/api/v1/convites").json()
    assert any(c["codigo"] == codigo for c in listagem)


def test_revogar_convite_via_api(client):
    convite = client.post("/api/v1/convites", json={"papel_concedido": "user"}).json()

    resposta = client.post(f"/api/v1/convites/{convite['codigo']}/revogar")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "revogado"


def test_convite_exige_papel_admin_ou_super_admin(client, criar_usuario_autenticado):
    """E4-H4-like — só admin/super_admin geram convite."""
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="semadmin@teste.com.br")

    resposta = client.post("/api/v1/convites", json={"papel_concedido": "user"}, headers=headers_user)

    assert resposta.status_code == 403


def test_registrar_via_convite_normal_retorna_licenca_ativa(client, db_session):
    """A fixture `client` já representa um tenant pagante (Onda H) —
    prova que o token de resposta reflete isso, ao contrário do fluxo de
    convite-vitrine (testado abaixo)."""
    convite = auth_service.gerar_convite(db_session, TENANT_ID, None, "user", validade_horas=24)

    resposta = client.post(
        "/api/v1/auth/registrar",
        json={
            "codigo_convite": convite.codigo,
            "nome": "Novo Pagante",
            "email": "novo-pagante@teste.com.br",
            "senha": "senha123",
            "aceite_termos": True,
        },
    )

    assert resposta.status_code == 201
    assert resposta.json()["tem_licenca_ativa"] is True


def test_convite_vitrine_qualquer_usuario_pode_gerar_sem_papel_admin(client, criar_usuario_autenticado):
    """Onda H: diferente do convite de usuário, convite-vitrine não exige
    papel admin/super_admin — decisão do produto é permitir crescimento
    peer-to-peer."""
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="convida-vitrine@teste.com.br")

    resposta = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}, headers=headers_user)

    assert resposta.status_code == 201
    assert resposta.json()["status"] == "disponivel"


def test_aceitar_convite_vitrine_cria_tenant_sem_licenca_e_loga(client):
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Parceira Convidada Ltda",
            "nome_admin": "Admin Parceira",
            "email_admin": "admin@parceira.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["tem_licenca_ativa"] is False
    assert corpo["usuario"]["papel"] == "admin"
    assert corpo["usuario"]["tenant_id"] != TENANT_ID


def test_tenant_vitrine_acessa_rede_social_mas_nao_modulo_pago(client):
    """O coração da Onda H: sem licença, `/rede-social/*` funciona e
    `/icp` (módulo pago) devolve 403 — mesmo com token válido."""
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    token = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Vitrine Sem Licenca Ltda",
            "nome_admin": "Admin",
            "email_admin": "vitrine-sem-licenca@teste.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
        },
    ).json()["access_token"]
    headers_vitrine = {"Authorization": f"Bearer {token}"}

    resposta_rede_social = client.get("/api/v1/rede-social/perfil", headers=headers_vitrine)
    assert resposta_rede_social.status_code == 200

    resposta_icp = client.get("/api/v1/icp", headers=headers_vitrine)
    assert resposta_icp.status_code == 403


def test_convite_vitrine_usado_duas_vezes_via_api_falha(client):
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    payload = {
        "codigo_convite": convite["codigo"],
        "razao_social": "Primeira Vez Ltda",
        "nome_admin": "A",
        "email_admin": "primeira-vez@teste.com.br",
        "senha_admin": "senha123",
        "aceite_termos": True,
    }
    client.post("/api/v1/auth/registrar-vitrine", json=payload)

    payload["email_admin"] = "segunda-vez@teste.com.br"
    resposta = client.post("/api/v1/auth/registrar-vitrine", json=payload)

    assert resposta.status_code == 409


def test_login_bloqueia_apos_muitas_tentativas(client, db_session):
    """Sem isso, força bruta contra a senha de qualquer usuário era viável
    (achado do raio-X de segurança) — POST /auth/login aceitava tentativas
    ilimitadas."""
    _criar_usuario_senha(db_session, "forca-bruta@teste.com.br", "senha-correta")

    for _ in range(5):
        resposta = client.post(
            "/api/v1/auth/login", json={"email": "forca-bruta@teste.com.br", "senha": "errada"}
        )
        assert resposta.status_code == 401

    bloqueado = client.post(
        "/api/v1/auth/login", json={"email": "forca-bruta@teste.com.br", "senha": "senha-correta"}
    )

    assert bloqueado.status_code == 429
