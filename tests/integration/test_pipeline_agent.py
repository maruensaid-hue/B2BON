from app.models.usuario import Usuario
from app.services import auth_service

TENANT_SEM_LICENCA = "tenant-sem-licenca"


def _criar_negocio_via_api(client, nome_conta: str = "Conta Pipeline") -> int:
    conta = client.post("/api/v1/leads/contas", json={"nome": nome_conta}).json()
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": "Decisor Teste"}).json()
    negocio = client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta["id"], "decisor_id": decisor["id"], "nome": "Negócio via API", "valor": 5000},
    ).json()
    return negocio["id"]


def test_riscos_pipeline_traz_negocio_sem_decision_maker_e_sem_proximo_passo(client):
    _criar_negocio_via_api(client)

    resposta = client.get("/api/v1/inteligencia-rede/riscos-pipeline")

    assert resposta.status_code == 200
    riscos = resposta.json()
    assert len(riscos) == 1
    assert any("decision_maker" in r.lower() for r in riscos[0]["riscos"])
    assert any("próximo passo" in r.lower() for r in riscos[0]["riscos"])


def test_riscos_pipeline_exige_licenca(client, db_session):
    usuario = Usuario(
        tenant_id=TENANT_SEM_LICENCA, nome="Sem Licença", email="admin@semlicenca.com.br", papel="admin", ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    headers_sem_licenca = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}

    resposta = client.get("/api/v1/inteligencia-rede/riscos-pipeline", headers=headers_sem_licenca)

    assert resposta.status_code == 403
