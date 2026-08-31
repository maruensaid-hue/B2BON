import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
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


def test_registrar_vitrine_sem_aceitar_termos_via_api_falha(client, criar_plano):
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    plano = criar_plano()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Sem Aceite Vitrine Ltda",
            "nome_admin": "Admin",
            "email_admin": "sem-aceite-vitrine@teste.com.br",
            "senha_admin": "senha123",
            "aceite_termos": False,
            "plano_id": plano.id,
        },
    )

    assert resposta.status_code == 422


def test_gerar_convite_vitrine_sem_email_nao_envia(client, fake_email):
    resposta = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24})

    assert resposta.status_code == 201
    assert fake_email.envios == []


def test_gerar_convite_vitrine_com_email_envia_convite(client, fake_email):
    resposta = client.post(
        "/api/v1/convites/vitrine",
        json={"validade_horas": 24, "email_destinatario": "convidado@teste.com.br"},
    )

    assert resposta.status_code == 201
    assert len(fake_email.envios) == 1
    envio = fake_email.envios[0]
    assert envio["destinatario"] == "convidado@teste.com.br"
    codigo = resposta.json()["codigo"]
    assert f"/convite-vitrine/{codigo}" in envio["corpo"]


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


def test_aceitar_convite_vitrine_cria_licenca_pendente_de_pagamento_e_loga(client, criar_plano):
    """Raio-X de produção: cadastro self-service agora escolhe um plano e
    abre uma cobrança — a licença nasce `pendente_pagamento` (não mais
    "sem licença" para sempre, comportamento anterior da Onda H)."""
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    plano = criar_plano()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Parceira Convidada Ltda",
            "nome_admin": "Admin Parceira",
            "email_admin": "admin@parceira.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
            "plano_id": plano.id,
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["tem_licenca_ativa"] is False
    assert corpo["checkout_url"] is not None
    assert corpo["usuario"]["papel"] == "admin"
    assert corpo["usuario"]["tenant_id"] != TENANT_ID


def test_tenant_vitrine_acessa_rede_social_mas_nao_modulo_pago(client, criar_plano):
    """O coração da Onda H: com a licença ainda `pendente_pagamento`,
    `/rede-social/*` funciona e `/icp` (módulo pago) devolve 403 — mesmo
    com token válido."""
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    plano = criar_plano()
    token = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Vitrine Sem Licenca Ltda",
            "nome_admin": "Admin",
            "email_admin": "vitrine-sem-licenca@teste.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
            "plano_id": plano.id,
        },
    ).json()["access_token"]
    headers_vitrine = {"Authorization": f"Bearer {token}"}

    resposta_rede_social = client.get("/api/v1/rede-social/perfil", headers=headers_vitrine)
    assert resposta_rede_social.status_code == 200

    resposta_icp = client.get("/api/v1/icp", headers=headers_vitrine)
    assert resposta_icp.status_code == 403


def test_convite_vitrine_usado_duas_vezes_via_api_falha(client, criar_plano):
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    plano = criar_plano()
    payload = {
        "codigo_convite": convite["codigo"],
        "razao_social": "Primeira Vez Ltda",
        "nome_admin": "A",
        "email_admin": "primeira-vez@teste.com.br",
        "senha_admin": "senha123",
        "aceite_termos": True,
        "plano_id": plano.id,
    }
    client.post("/api/v1/auth/registrar-vitrine", json=payload)

    payload["email_admin"] = "segunda-vez@teste.com.br"
    resposta = client.post("/api/v1/auth/registrar-vitrine", json=payload)

    assert resposta.status_code == 409


def test_gerar_convite_gratuito_por_usuario_comum_e_negado(client, criar_usuario_autenticado):
    """Raio-X: só admin/super_admin pode gerar convite gratuito — sem
    essa trava, qualquer usuário comum poderia conceder plano "Teste"
    (sem checkout, sem expiração) pra terceiros à vontade."""
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="comum@teste.com.br")

    resposta = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24, "gratuito": True}, headers=headers_user)

    assert resposta.status_code == 403


def test_gerar_convite_gratuito_por_admin_funciona(client):
    """Client de teste já é super_admin por padrão."""
    resposta = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24, "gratuito": True})

    assert resposta.status_code == 201
    assert resposta.json()["gratuito"] is True


def test_info_convite_vitrine_expoe_se_e_gratuito(client):
    normal = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    gratuito = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24, "gratuito": True}).json()

    info_normal = client.get(f"/api/v1/convites/vitrine/{normal['codigo']}/info")
    info_gratuito = client.get(f"/api/v1/convites/vitrine/{gratuito['codigo']}/info")

    assert info_normal.status_code == 200
    assert info_normal.json() == {"status": "disponivel", "gratuito": False}
    assert info_gratuito.json() == {"status": "disponivel", "gratuito": True}


def test_info_convite_vitrine_inexistente_e_404(client):
    resposta = client.get("/api/v1/convites/vitrine/CODIGO-INEXISTENTE/info")
    assert resposta.status_code == 404


def test_aceitar_convite_gratuito_cria_licenca_ativa_sem_checkout_nem_expiracao(client, db_session, criar_plano):
    """O coração do raio-X: convite gratuito vira Licença "Teste" ativa,
    sem passar pelo checkout — e ignora qualquer plano_id que o cliente
    mande, pra ninguém conseguir se auto-conceder um plano pago de graça
    chamando a rota direto com um plano_id diferente."""
    plano_teste = criar_plano(nome="Teste", preco_mensal=0.0, visivel_self_service=False)
    plano_pago = criar_plano(nome="Starter Pago", preco_mensal=490.0)
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24, "gratuito": True}).json()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Empresa Teste Gratis Ltda",
            "nome_admin": "Admin Teste",
            "email_admin": "admin@testegratis.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
            "plano_id": plano_pago.id,  # tentativa de burlar — deve ser ignorado
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["tem_licenca_ativa"] is True
    assert corpo["checkout_url"] is None

    from app.models.licenca import Licenca

    licenca = db_session.query(Licenca).filter_by(tenant_id=corpo["usuario"]["tenant_id"]).one()
    assert licenca.status == "ativa"
    assert licenca.plano_id == plano_teste.id
    assert licenca.data_expiracao is None


def test_aceitar_convite_gratuito_cria_tenant_tipo_distribuidor(client, db_session, criar_plano):
    """Raio-X 2026-08-28: tenant cortesia (convite gratuito) precisa
    conseguir criar sub-tenants ("seus próprios clientes") — sem isso,
    nascia `tipo="cliente"` (folha, sem essa capacidade). Convite pago
    continua `tipo="cliente"`, sem mudança."""
    criar_plano(nome="Teste", preco_mensal=0.0, visivel_self_service=False)
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24, "gratuito": True}).json()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Empresa Cortesia Ltda",
            "nome_admin": "Admin Cortesia",
            "email_admin": "admin@cortesia.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
        },
    )

    from app.models.tenant import Tenant

    tenant_id = resposta.json()["usuario"]["tenant_id"]
    tenant = db_session.query(Tenant).filter_by(id=tenant_id).one()
    assert tenant.tipo == "distribuidor"
    assert tenant.tenant_pai_id is None


def test_aceitar_convite_pago_continua_criando_tenant_tipo_cliente(client, db_session, criar_plano):
    plano_pago = criar_plano(nome="Starter Comum", preco_mensal=490.0)
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Empresa Paga Ltda",
            "nome_admin": "Admin Paga",
            "email_admin": "admin@paga.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
            "plano_id": plano_pago.id,
        },
    )

    from app.models.tenant import Tenant

    tenant_id = resposta.json()["usuario"]["tenant_id"]
    tenant = db_session.query(Tenant).filter_by(id=tenant_id).one()
    assert tenant.tipo == "cliente"


def test_registrar_vitrine_com_plano_nao_self_service_e_negado(client, criar_plano):
    """Mesmo num convite normal (não gratuito), o plano "Teste" não pode
    ser escolhido livremente — só via convite gratuito."""
    plano_teste = criar_plano(nome="Teste", preco_mensal=0.0, visivel_self_service=False)
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()

    resposta = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Tentativa Furar Fila Ltda",
            "nome_admin": "Admin",
            "email_admin": "furafila@teste.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
            "plano_id": plano_teste.id,
        },
    )

    assert resposta.status_code == 409


def test_planos_apenas_self_service_esconde_plano_teste(client, criar_plano):
    criar_plano(nome="Teste", preco_mensal=0.0, visivel_self_service=False)
    criar_plano(nome="Starter Visivel", preco_mensal=490.0)

    todos = client.get("/api/v1/planos").json()
    so_self_service = client.get("/api/v1/planos", params={"apenas_self_service": True}).json()

    assert any(p["nome"] == "Teste" for p in todos)
    assert not any(p["nome"] == "Teste" for p in so_self_service)
    assert any(p["nome"] == "Starter Visivel" for p in so_self_service)


def _assinatura_valida(payment_id: str, request_id: str, ts: str, segredo: str) -> str:
    manifest = f"id:{payment_id.lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(segredo.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


@pytest.fixture()
def com_segredo_webhook_mercadopago(monkeypatch: pytest.MonkeyPatch) -> str:
    segredo = "segredo-webhook-teste"
    monkeypatch.setattr(settings, "mercadopago_webhook_secret", segredo)
    return segredo


def test_webhook_mercadopago_com_assinatura_valida_ativa_licenca(
    client, criar_plano, fake_payment, com_segredo_webhook_mercadopago
):
    """Fim-a-fim: cadastro self-service com plano fica `pendente_pagamento`
    até o webhook confirmar — depois disso, o módulo pago libera."""
    convite = client.post("/api/v1/convites/vitrine", json={"validade_horas": 24}).json()
    plano = criar_plano()
    resposta_cadastro = client.post(
        "/api/v1/auth/registrar-vitrine",
        json={
            "codigo_convite": convite["codigo"],
            "razao_social": "Fim A Fim Ltda",
            "nome_admin": "Admin",
            "email_admin": "fim-a-fim@teste.com.br",
            "senha_admin": "senha123",
            "aceite_termos": True,
            "plano_id": plano.id,
        },
    )
    token = resposta_cadastro.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/licenca-status", headers=headers).json()["status"] == "pendente_pagamento"

    preferencia_id = next(iter(fake_payment._preferencias))
    payment_id_externo = fake_payment.aprovar(preferencia_id)
    x_signature = _assinatura_valida(payment_id_externo, "req-teste", "1700000000", com_segredo_webhook_mercadopago)

    resposta_webhook = client.post(
        f"/api/v1/webhooks/mercadopago?data.id={payment_id_externo}",
        headers={"x-signature": x_signature, "x-request-id": "req-teste"},
    )

    assert resposta_webhook.status_code == 200
    assert client.get("/api/v1/auth/licenca-status", headers=headers).json()["status"] == "ativa"
    assert client.get("/api/v1/icp", headers=headers).status_code == 200


def test_webhook_mercadopago_com_assinatura_invalida_e_rejeitado(client, fake_payment, com_segredo_webhook_mercadopago):
    """Sem isso, qualquer um poderia forjar um POST de "aprovado" e ganhar
    licença de graça."""
    resposta = client.post(
        "/api/v1/webhooks/mercadopago?data.id=123456",
        headers={"x-signature": "ts=1700000000,v1=forjado", "x-request-id": "req-forjado"},
    )

    assert resposta.status_code == 403


def test_webhook_mercadopago_sem_segredo_configurado_e_rejeitado(client, fake_payment):
    """`mercadopago_webhook_secret` vazio nunca autoriza — mesmo padrão do `cron_secret`."""
    resposta = client.post(
        "/api/v1/webhooks/mercadopago?data.id=123456",
        headers={"x-signature": "ts=1700000000,v1=qualquercoisa", "x-request-id": "req-sem-segredo"},
    )

    assert resposta.status_code == 403


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
