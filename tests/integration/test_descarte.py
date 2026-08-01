from app.providers.account_data.base import ContaCandidata

TENANT_ID = "tenant-teste"


def _candidato(cnpj: str) -> ContaCandidata:
    return ContaCandidata(
        cnpj=cnpj,
        razao_social="Empresa Teste",
        cnae_principal="6201500",
        porte="PEQUENO",
        uf="SP",
        situacao_cadastral="ATIVA",
        fonte="receita_federal_cnpj",
    )


def _gerar_conta(client, icp_id: int, fake_account_data, cnpj: str) -> dict:
    fake_account_data.candidatos = [_candidato(cnpj)]
    return client.post(f"/api/v1/icp/{icp_id}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]


def test_descartar_sem_motivo_retorna_422(client, criar_icp, fake_account_data):
    icp = criar_icp()
    conta = _gerar_conta(client, icp["id"], fake_account_data, "11222333000191")

    resposta = client.post(f"/api/v1/contas/{conta['id']}/descartar", json={})

    assert resposta.status_code == 422


def test_descartar_seta_status_e_motivo(client, criar_icp, fake_account_data):
    """E2-H4: ações de priorizar/descartar com motivo obrigatório no descarte."""
    icp = criar_icp()
    conta = _gerar_conta(client, icp["id"], fake_account_data, "11222333000191")

    resposta = client.post(f"/api/v1/contas/{conta['id']}/descartar", json={"motivo": "sem fit com o ICP"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "descartada"
    assert corpo["motivo_descarte"] == "sem fit com o ICP"


def test_priorizar_seta_status(client, criar_icp, fake_account_data):
    icp = criar_icp()
    conta = _gerar_conta(client, icp["id"], fake_account_data, "11222333000191")

    resposta = client.post(f"/api/v1/contas/{conta['id']}/priorizar")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "priorizada"


def test_descartes_repetidos_penalizam_score_de_novo_candidato(client, criar_icp, fake_account_data):
    """E2-H4: descartes alimentam o refinamento do score de aderência."""
    icp = criar_icp()

    conta1 = _gerar_conta(client, icp["id"], fake_account_data, "11111111000101")
    assert conta1["score_aderencia"] == 1.0
    client.post(f"/api/v1/contas/{conta1['id']}/descartar", json={"motivo": "sem fit"})

    conta2 = _gerar_conta(client, icp["id"], fake_account_data, "22222222000102")
    client.post(f"/api/v1/contas/{conta2['id']}/descartar", json={"motivo": "sem fit"})

    conta3 = _gerar_conta(client, icp["id"], fake_account_data, "33333333000103")

    assert conta3["score_aderencia"] == 0.9
