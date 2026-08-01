from app.providers.account_data.base import ContaCandidata

TENANT_ID = "tenant-teste"


def _agendar_e_realizar_qualificada(client, decisor_id: int) -> dict:
    proposta = client.post(
        f"/api/v1/decisores/{decisor_id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = proposta["horarios_propostos"][0]
    confirmada = client.post(
        f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario}
    ).json()
    client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "realizada"})
    client.post(
        f"/api/v1/reunioes/{confirmada['id']}/confirmar-qualificacao", json={"qualificada": True, "motivo": None}
    )
    return confirmada


def test_metrica_norte_conta_apenas_reunioes_qualificadas_realizadas(client, criar_conta_com_decisor):
    """E8-H1: métrica-norte com fonte exclusiva nos registros automáticos do CRM."""
    conta, decisor = criar_conta_com_decisor()
    _agendar_e_realizar_qualificada(client, decisor.id)

    resposta = client.get("/api/v1/painel/metrica-norte")

    assert resposta.status_code == 200
    assert resposta.json()["valor_mes_atual"] == 1


def test_metrica_norte_nao_conta_reuniao_sem_qualificacao_confirmada(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    proposta = client.post(
        f"/api/v1/decisores/{decisor.id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = proposta["horarios_propostos"][0]
    confirmada = client.post(
        f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario}
    ).json()
    client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "realizada"})
    # qualificação nunca confirmada pelo vendedor

    corpo = client.get("/api/v1/painel/metrica-norte").json()

    assert corpo["valor_mes_atual"] == 0


def test_meta_configuravel_por_assinante(client, criar_conta_com_decisor):
    """E8-H1: card principal com valor do mês corrente, meta e comparativo."""
    conta, decisor = criar_conta_com_decisor()
    _agendar_e_realizar_qualificada(client, decisor.id)

    definida = client.put("/api/v1/painel/configuracao-meta", json={"meta_mensal_reunioes": 10})
    assert definida.status_code == 200
    assert definida.json()["meta_mensal_reunioes"] == 10
    assert client.get("/api/v1/painel/configuracao-meta").json()["meta_mensal_reunioes"] == 10

    corpo = client.get("/api/v1/painel/metrica-norte").json()
    assert corpo["meta"] == 10
    assert corpo["valor_mes_atual"] == 1


def test_indicadores_expoe_energia_e_atrito_por_periodo_configuravel(client, criar_icp, fake_account_data):
    """E8-H2: indicadores de energia/atrito, com origem da oportunidade e período configurável."""
    icp = criar_icp()
    fake_account_data.candidatos = [
        ContaCandidata(
            cnpj="11222333000191",
            razao_social="Alpha Tech",
            cnae_principal="6201500",
            porte="PEQUENO",
            uf="SP",
            situacao_cadastral="ATIVA",
        )
    ]
    client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})

    resposta = client.get("/api/v1/painel/indicadores", params={"data_inicio": "2020-01-01", "data_fim": "2030-01-01"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["periodo_inicio"] == "2020-01-01"
    assert corpo["periodo_fim"] == "2030-01-01"
    assert corpo["energia"]["origem_oportunidade"] == {"prospeccao_ativa": 1, "indicacao": 0}
    assert "taxa_no_show" in corpo["atrito"]


def test_export_csv_dos_indicadores(client):
    resposta = client.get("/api/v1/painel/indicadores/export.csv")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "indicador,valor" in resposta.text
