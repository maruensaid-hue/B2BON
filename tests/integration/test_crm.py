from datetime import UTC, datetime

from app.api.deps import get_crm_provider
from app.main import app
from app.providers.crm.nucleo import NucleoCrmProvider

TENANT_ID = "tenant-teste"


def test_estagios_padrao_via_api(client):
    resposta = client.get("/api/v1/crm/estagios")

    assert resposta.status_code == 200
    estagios = resposta.json()
    assert len(estagios) == 5
    assert {e["tipo"] for e in estagios} == {"aberto", "ganho", "perdido"}


def test_criar_e_listar_negocio_via_api(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()

    criado = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio API", "valor": 5000.0}
    )
    assert criado.status_code == 201
    assert criado.json()["origem"] == "manual"

    listagem = client.get("/api/v1/crm/negocios").json()
    assert any(n["nome"] == "Negócio API" for n in listagem)


def test_listar_negocios_filtra_por_conta(client, criar_conta_com_decisor):
    """Necessário para a página "Ações na conta" (E-Leads) mostrar só as
    oportunidades daquela conta, não o kanban inteiro do tenant."""
    conta_a, _ = criar_conta_com_decisor()
    conta_b, _ = criar_conta_com_decisor()
    client.post("/api/v1/crm/negocios", json={"conta_id": conta_a.id, "nome": "Negócio A", "valor": 100.0})
    client.post("/api/v1/crm/negocios", json={"conta_id": conta_b.id, "nome": "Negócio B", "valor": 200.0})

    resposta = client.get(f"/api/v1/crm/negocios?conta_id={conta_a.id}").json()

    assert [n["nome"] for n in resposta] == ["Negócio A"]


def test_mover_estagio_via_api_marca_cliente(client, criar_conta_com_decisor):
    """E2-H4-like (Onda B): mover para estágio "ganho" marca a conta como cliente."""
    conta, _ = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 1000.0}
    ).json()
    estagio_ganho = next(e for e in client.get("/api/v1/crm/estagios").json() if e["tipo"] == "ganho")

    resposta = client.put(f"/api/v1/crm/negocios/{negocio['id']}/estagio", json={"estagio_id": estagio_ganho["id"]})

    assert resposta.status_code == 200
    assert resposta.json()["ganho_em"] is not None


def test_mover_estagio_para_perdido_sem_motivo_via_api_falha(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 1000.0}
    ).json()
    estagio_perdido = next(e for e in client.get("/api/v1/crm/estagios").json() if e["tipo"] == "perdido")

    resposta = client.put(f"/api/v1/crm/negocios/{negocio['id']}/estagio", json={"estagio_id": estagio_perdido["id"]})

    assert resposta.status_code == 422


def test_excluir_negocio_via_api(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio a excluir", "valor": 1000.0}
    ).json()

    resposta = client.delete(f"/api/v1/crm/negocios/{negocio['id']}")

    assert resposta.status_code == 204
    assert client.get("/api/v1/crm/negocios", params={"conta_id": conta.id}).json() == []
    # Reexcluir o mesmo id agora não encontra mais o negócio.
    assert client.delete(f"/api/v1/crm/negocios/{negocio['id']}").status_code == 404


def test_atividade_via_api(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 100.0}
    ).json()

    criada = client.post(
        f"/api/v1/crm/negocios/{negocio['id']}/atividades", json={"tipo": "ligacao", "descricao": "Falei com o cliente"}
    )
    assert criada.status_code == 201

    listagem = client.get(f"/api/v1/crm/negocios/{negocio['id']}/atividades").json()
    # +1 automática ("negócio criado") além da registrada manualmente aqui.
    assert len(listagem) == 2
    assert any(a["descricao"] == "Falei com o cliente" for a in listagem)


def test_cancelar_cliente_via_api(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 100.0}
    ).json()
    estagio_ganho = next(e for e in client.get("/api/v1/crm/estagios").json() if e["tipo"] == "ganho")
    client.put(f"/api/v1/crm/negocios/{negocio['id']}/estagio", json={"estagio_id": estagio_ganho["id"]})

    resposta = client.post(f"/api/v1/crm/contas/{conta.id}/cancelar-cliente", json={"motivo": "Insatisfeito"})

    assert resposta.status_code == 200
    assert resposta.json()["cliente_cancelado_em"] is not None


def test_cancelar_cliente_sem_ser_cliente_falha(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()

    resposta = client.post(f"/api/v1/crm/contas/{conta.id}/cancelar-cliente", json={})

    assert resposta.status_code == 409


def test_custo_aquisicao_via_api(client):
    resposta = client.put("/api/v1/crm/custo-aquisicao", json={"periodo": "2026-01", "valor": 5000.0})

    assert resposta.status_code == 200
    assert resposta.json()["valor"] == 5000.0


def test_dashboard_funil_via_api(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    client.post("/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 100.0})

    resposta = client.get("/api/v1/crm/dashboard/funil")

    assert resposta.status_code == 200
    assert len(resposta.json()["estagios"]) == 5


def test_dashboard_atividade_via_api(client, criar_conta_com_decisor):
    conta, _ = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "nome": "Negócio", "valor": 0.0}
    ).json()
    client.post(f"/api/v1/crm/negocios/{negocio['id']}/atividades", json={"tipo": "nota", "descricao": "Nota"})

    resposta = client.get("/api/v1/crm/dashboard/atividade")

    assert resposta.status_code == 200
    # +1 automática ("negócio criado") além da atividade manual registrada aqui.
    assert resposta.json()["total_equipe"] == 2


def test_dashboard_economia_via_api(client):
    periodo_atual = datetime.now(UTC).strftime("%Y-%m")

    resposta = client.get("/api/v1/crm/dashboard/economia", params={"periodo": periodo_atual})

    assert resposta.status_code == 200
    assert resposta.json()["periodo"] == periodo_atual


def test_dashboard_flywheel_via_api(client):
    resposta = client.get("/api/v1/crm/dashboard/flywheel")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "metrica_norte" in corpo
    assert "funil" in corpo


def test_retroalimentacao_reuniao_confirmada_cria_negocio_real(client, db_session, criar_conta_com_decisor):
    """Onda B: o que acontece no PREDATOR aparece no CRM sem nenhuma
    mudança em reuniao_service.py — usa o NucleoCrmProvider real em vez
    do fake_crm padrão da fixture, só neste teste."""
    conta, decisor = criar_conta_com_decisor()
    app.dependency_overrides[get_crm_provider] = lambda: NucleoCrmProvider(db_session)

    proposta = client.post(
        f"/api/v1/decisores/{decisor.id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = proposta["horarios_propostos"][0]
    client.post(f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario})

    negocios = client.get("/api/v1/crm/negocios").json()
    negocio_da_reuniao = next(n for n in negocios if n["conta_id"] == conta.id and n["origem"] == "predator_reuniao")

    assert negocio_da_reuniao is not None
