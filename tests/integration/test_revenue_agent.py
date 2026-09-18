from app.models.usuario import Usuario
from app.services import auth_service

TENANT_SEM_LICENCA = "tenant-sem-licenca"


def _criar_oferta_via_api(client, nome: str = "Oferta Teste") -> int:
    resposta = client.post("/api/v1/ofertas", json={"nome": nome, "descricao": "desc"})
    return resposta.json()["id"]


def _criar_negocio_via_api(client, oferta_id: int | None = None) -> tuple[int, int]:
    conta = client.post("/api/v1/leads/contas", json={"nome": "Conta Revenue"}).json()
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": "Decisor Teste"}).json()
    dados = {"conta_id": conta["id"], "decisor_id": decisor["id"], "nome": "Negócio via API", "valor": 5000}
    if oferta_id is not None:
        dados["oferta_id"] = oferta_id
    negocio = client.post("/api/v1/crm/negocios", json=dados).json()
    return conta["id"], negocio["id"]


def test_criar_negocio_com_oferta_id_via_api(client):
    oferta_id = _criar_oferta_via_api(client)
    conta_id, negocio_id = _criar_negocio_via_api(client, oferta_id=oferta_id)

    negocios = client.get("/api/v1/crm/negocios").json()
    negocio = next(n for n in negocios if n["id"] == negocio_id)
    assert negocio["oferta_id"] == oferta_id


def test_atribuicao_receita_via_api(client):
    resposta = client.get("/api/v1/inteligencia-rede/atribuicao-receita")

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["contas_geradas_pela_rede"] == 0
    assert dados["taxa_conversao_sinais"] == 0.0


def test_sugestoes_expansao_via_api(client):
    oferta_id = _criar_oferta_via_api(client)
    conta_id, negocio_id = _criar_negocio_via_api(client)
    estagios = client.get("/api/v1/crm/estagios").json()
    estagio_ganho = next(e for e in estagios if e["tipo"] == "ganho")
    client.put(f"/api/v1/crm/negocios/{negocio_id}/estagio", json={"estagio_id": estagio_ganho["id"]})

    resposta = client.get("/api/v1/inteligencia-rede/sugestoes-expansao")

    assert resposta.status_code == 200
    sugestoes = resposta.json()
    assert any(s["conta_id"] == conta_id and s["oferta_id"] == oferta_id for s in sugestoes)


def test_atribuicao_receita_exige_licenca(client, db_session):
    usuario = Usuario(
        tenant_id=TENANT_SEM_LICENCA, nome="Sem Licença", email="admin@semlicenca.com.br", papel="admin", ativo=True
    )
    db_session.add(usuario)
    db_session.commit()
    headers_sem_licenca = {"Authorization": f"Bearer {auth_service.gerar_token(usuario)}"}

    resposta = client.get("/api/v1/inteligencia-rede/atribuicao-receita", headers=headers_sem_licenca)

    assert resposta.status_code == 403
