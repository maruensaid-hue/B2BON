from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service


def _criar_admin(db_session, tenant_id: str, tipo: str) -> dict[str, str]:
    plano = Plano(nome=f"Plano {tenant_id}", franquia_contas_mes=500, max_usuarios=20, preco_mensal=490.0)
    db_session.add(plano)
    db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo))
    db_session.flush()
    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    usuario = Usuario(tenant_id=tenant_id, nome="Admin", email=f"admin@{tenant_id}.com.br", papel="admin", ativo=True)
    db_session.add(usuario)
    db_session.commit()
    token = auth_service.gerar_token(usuario)
    return {"Authorization": f"Bearer {token}"}


def test_distribuidor_gera_chave_e_ve_o_valor_completo_uma_vez(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-int1", tipo="distribuidor")

    resposta = client.post("/api/v1/integracoes/chaves-api", json={"nome": "ERP"}, headers=headers)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["chave"].startswith("b2bon_")
    assert corpo["prefixo"] == corpo["chave"][:12]

    listagem = client.get("/api/v1/integracoes/chaves-api", headers=headers).json()
    assert len(listagem) == 1
    assert "chave" not in listagem[0]


def test_revendedor_nao_acessa_integracoes(client, db_session) -> None:
    """Só Distribuidor tem chave de API — decisão validada com o usuário."""
    headers = _criar_admin(db_session, "revenda-int1", tipo="revendedor")

    resposta = client.get("/api/v1/integracoes/chaves-api", headers=headers)

    assert resposta.status_code == 403


def test_revogar_chave(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-int2", tipo="distribuidor")
    chave_id = client.post("/api/v1/integracoes/chaves-api", json={"nome": "ERP"}, headers=headers).json()["id"]

    resposta = client.delete(f"/api/v1/integracoes/chaves-api/{chave_id}", headers=headers)

    assert resposta.status_code == 200
    assert resposta.json()["revogada_em"] is not None


def test_configurar_webhook_devolve_segredo_uma_vez(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-int3", tipo="distribuidor")

    resposta = client.put(
        "/api/v1/integracoes/webhook", json={"url_callback": "https://exemplo.com.br/webhook"}, headers=headers
    )

    assert resposta.status_code == 200
    assert "segredo" in resposta.json()

    consulta = client.get("/api/v1/integracoes/webhook", headers=headers).json()
    assert "segredo" not in consulta
    assert consulta["url_callback"] == "https://exemplo.com.br/webhook"


def test_desativar_webhook(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-int4", tipo="distribuidor")
    client.put("/api/v1/integracoes/webhook", json={"url_callback": "https://exemplo.com.br/webhook"}, headers=headers)

    resposta = client.delete("/api/v1/integracoes/webhook", headers=headers)

    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is False
