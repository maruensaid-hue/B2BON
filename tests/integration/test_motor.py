from datetime import UTC, datetime, timedelta

import pytest

from app.models.licenca import Licenca
from app.models.plano import Plano

TENANT_ID_PADRAO = "tenant-teste"


def _criar_plano(db_session, nome: str, preco_mensal: float = 800.0) -> int:
    plano = Plano(nome=nome, franquia_contas_mes=200, max_usuarios=10, preco_mensal=preco_mensal)
    db_session.add(plano)
    db_session.commit()
    return plano.id


def _criar_tenant_via_api(client, db_session, tenant_id: str, preco_mensal: float = 800.0) -> str:
    plano_id = _criar_plano(db_session, nome=f"Plano-{tenant_id}", preco_mensal=preco_mensal)
    resposta = client.post(
        "/api/v1/admin/tenants",
        json={
            "tenant_id": tenant_id,
            "razao_social": f"Empresa {tenant_id}",
            "plano_id": plano_id,
            "nome_admin": "Admin",
            "email_admin": f"admin@{tenant_id}.com.br",
            "senha_admin": "senha123",
        },
    )
    assert resposta.status_code == 201, resposta.text
    return tenant_id


def test_rotas_motor_bloqueadas_para_nao_super_admin(client, criar_usuario_autenticado):
    headers_admin = criar_usuario_autenticado(TENANT_ID_PADRAO, papel="admin", email="admin-motor@teste.com.br")

    assert client.get("/api/v1/motor/dashboard", headers=headers_admin).status_code == 403
    assert client.get("/api/v1/motor/saude-tenants", headers=headers_admin).status_code == 403
    assert (
        client.post(
            "/api/v1/motor/interacoes",
            json={"tenant_id": TENANT_ID_PADRAO, "tipo": "contato"},
            headers=headers_admin,
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/motor/tenants/{TENANT_ID_PADRAO}/interacoes", headers=headers_admin).status_code == 403
    assert client.get(f"/api/v1/motor/tenants/{TENANT_ID_PADRAO}/score-risco", headers=headers_admin).status_code == 403
    assert (
        client.get(f"/api/v1/motor/tenants/{TENANT_ID_PADRAO}/script-resgate", headers=headers_admin).status_code
        == 403
    )


def test_registrar_e_listar_interacao_via_api(client, db_session):
    tenant_id = _criar_tenant_via_api(client, db_session, "empresa-motor-1")

    resposta = client.post(
        "/api/v1/motor/interacoes",
        json={"tenant_id": tenant_id, "tipo": "reclamacao", "descricao": "Reclamou de lentidão no suporte"},
    )
    assert resposta.status_code == 201
    assert resposta.json()["tipo"] == "reclamacao"

    listagem = client.get(f"/api/v1/motor/tenants/{tenant_id}/interacoes")
    assert listagem.status_code == 200
    assert len(listagem.json()) == 1


def test_score_risco_via_api(client, db_session):
    tenant_id = _criar_tenant_via_api(client, db_session, "empresa-motor-2")
    client.post("/api/v1/motor/interacoes", json={"tenant_id": tenant_id, "tipo": "mencionou_concorrente"})

    resposta = client.get(f"/api/v1/motor/tenants/{tenant_id}/score-risco")

    assert resposta.status_code == 200
    assert resposta.json()["sinais"]["mencionou_concorrente"] == 20


def test_saude_tenants_e_dashboard_via_api(client, db_session):
    tenant_id = _criar_tenant_via_api(client, db_session, "empresa-motor-3", preco_mensal=1000.0)
    licenca = db_session.query(Licenca).filter_by(tenant_id=tenant_id).one()
    licenca.data_inicio = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)
    db_session.commit()

    for _ in range(3):
        client.post("/api/v1/motor/interacoes", json={"tenant_id": tenant_id, "tipo": "reclamacao"})

    ranking = client.get("/api/v1/motor/saude-tenants").json()
    entrada = next(item for item in ranking if item["tenant_id"] == tenant_id)
    assert entrada["classificacao"] in ("atencao", "critico")
    assert entrada["valor_em_risco"] == pytest.approx(1000.0 * 3.0, rel=0.05)

    dashboard = client.get("/api/v1/motor/dashboard").json()
    assert dashboard["total_tenants"] >= 1
    assert dashboard["valor_total_em_risco"] >= entrada["valor_em_risco"]


def test_script_resgate_via_api_usa_llm(client, db_session, fake_llm):
    tenant_id = _criar_tenant_via_api(client, db_session, "empresa-motor-4")
    client.post("/api/v1/motor/interacoes", json={"tenant_id": tenant_id, "tipo": "reclamacao"})
    fake_llm.definir_respostas(["Olá! Notamos sua reclamação recente e gostaríamos de ajudar."])

    resposta = client.get(f"/api/v1/motor/tenants/{tenant_id}/script-resgate")

    assert resposta.status_code == 200
    assert resposta.json()["script"] == "Olá! Notamos sua reclamação recente e gostaríamos de ajudar."
    assert len(fake_llm.chamadas) == 1
