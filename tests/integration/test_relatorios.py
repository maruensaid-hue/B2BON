from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auth_service


def _criar_admin(db_session, tenant_id: str, tipo: str) -> dict[str, str]:
    plano = Plano(nome=f"Plano {tenant_id}", franquia_contas_mes=100, max_usuarios=10, preco_mensal=490.0)
    db_session.add(plano)
    db_session.flush()
    db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo))
    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    usuario = Usuario(tenant_id=tenant_id, nome="Admin", email=f"admin@{tenant_id}.com.br", papel="admin", ativo=True)
    db_session.add(usuario)
    db_session.commit()
    token = auth_service.gerar_token(usuario)
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_distribuidor(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-rel1", tipo="distribuidor")

    resposta = client.get("/api/v1/relatorios/dashboard?periodo_dias=7", headers=headers)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "atual" in corpo and "anterior" in corpo
    assert corpo["atual"]["tenants_ativos_distribuidor"] == 1


def test_dashboard_bloqueado_pra_cliente_comum(client, db_session) -> None:
    headers = _criar_admin(db_session, "cliente-rel1", tipo="cliente")

    resposta = client.get("/api/v1/relatorios/dashboard", headers=headers)

    assert resposta.status_code == 403


def test_configuracao_inexistente_retorna_404(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-rel2", tipo="distribuidor")

    resposta = client.get("/api/v1/relatorios/configuracao", headers=headers)

    assert resposta.status_code == 404


def test_definir_e_obter_configuracao(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-rel3", tipo="distribuidor")

    resposta_put = client.put("/api/v1/relatorios/configuracao", json={"cadencia": "semanal"}, headers=headers)
    assert resposta_put.status_code == 200
    assert resposta_put.json()["cadencia"] == "semanal"

    resposta_get = client.get("/api/v1/relatorios/configuracao", headers=headers)
    assert resposta_get.status_code == 200
    assert resposta_get.json()["cadencia"] == "semanal"


def test_definir_configuracao_cadencia_invalida(client, db_session) -> None:
    headers = _criar_admin(db_session, "distribuidor-rel4", tipo="distribuidor")

    resposta = client.put("/api/v1/relatorios/configuracao", json={"cadencia": "trimestral"}, headers=headers)

    assert resposta.status_code == 422
