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


def test_fit_icp_rede_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    icp_id = _criar_icp(client)
    client.put(
        "/api/v1/rede-social/perfil",
        json={"nome_exibicao": "Empresa B", "cnae_principal": "8610-1/01", "porte": "grande", "sede_uf": "SP"},
        headers=headers_b,
    )

    resposta = client.get(f"/api/v1/inteligencia-rede/fit-icp?icp_id={icp_id}")

    assert resposta.status_code == 200
    resultado = resposta.json()
    assert len(resultado) == 1
    assert resultado[0]["tenant_id_candidato"] == TENANT_B
    assert resultado[0]["fit_score"] == 1.0


def test_fit_icp_rede_exige_licenca(client, db_session):
    """Tenant sem nenhuma `Licenca` (ex.: entrou só pela Rede Social via
    convite, Onda H) não pode acessar `/inteligencia-rede/*` — distinto
    de `criar_usuario_autenticado`, que sempre garante uma licença ativa
    (`_garantir_licenca_ativa`), por isso o usuário é criado direto
    aqui, sem passar por ela."""
    usuario = Usuario(
        tenant_id=TENANT_SEM_LICENCA, nome="Sem Licença", email="admin@semlicenca.com.br", papel="admin", ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    headers_sem_licenca = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}
    icp_id = _criar_icp(client)

    resposta = client.get(f"/api/v1/inteligencia-rede/fit-icp?icp_id={icp_id}", headers=headers_sem_licenca)

    assert resposta.status_code == 403


def test_fit_icp_rede_icp_inexistente_retorna_404(client):
    resposta = client.get("/api/v1/inteligencia-rede/fit-icp?icp_id=9999")

    assert resposta.status_code == 404
