from app.models.usuario import Usuario
from app.services import auth_service

TENANT_B = "tenant-outro"
TENANT_SEM_LICENCA = "tenant-sem-licenca-4b"


def _conectar_via_api(client, headers_b):
    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_b)


def test_listar_saude_relacionamentos_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.put("/api/v1/rede-social/perfil", json={"nome_exibicao": "Empresa B"}, headers=headers_b)
    _conectar_via_api(client, headers_b)

    resposta = client.get("/api/v1/inteligencia-rede/saude-relacionamentos")

    assert resposta.status_code == 200
    resultado = resposta.json()
    assert len(resultado) == 1
    assert resultado[0]["tenant_id_alvo"] == TENANT_B
    assert resultado[0]["classificacao"] == "sem_interacao"


def test_saude_relacionamentos_exige_licenca(client, db_session):
    """Tenant sem nenhuma `Licenca` (ex.: entrou só pela Rede Social via
    convite) não pode acessar `/inteligencia-rede/*` — mesmo padrão de
    `test_fit_icp_rede_exige_licenca` (Fase 3B)."""
    usuario = Usuario(
        tenant_id=TENANT_SEM_LICENCA, nome="Sem Licença", email="admin@semlicenca4b.com.br", papel="admin",
        ativo=True,
    )
    db_session.add(usuario)
    db_session.commit()
    headers_sem_licenca = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}

    resposta = client.get("/api/v1/inteligencia-rede/saude-relacionamentos", headers=headers_sem_licenca)

    assert resposta.status_code == 403
