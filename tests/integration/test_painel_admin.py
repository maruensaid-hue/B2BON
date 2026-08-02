from app.providers.account_data.base import ContaCandidata

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"


def _onboarding(client, headers: dict) -> None:
    client.post(
        "/api/v1/icp",
        json={
            "nome": "ICP", "segmento": "Tecnologia", "porte": "PEQUENO", "regiao": "SP",
            "dores": [], "gatilhos": [], "cnae_codigos": ["6201500"], "ufs": ["SP"],
        },
        headers=headers,
    )
    client.post(
        "/api/v1/ofertas",
        json={"nome": "Oferta", "descricao": "desc", "diferenciais": [], "provas_sociais": []},
        headers=headers,
    )
    client.put("/api/v1/comunicacao", json={"tom": "consultivo", "restricoes": []}, headers=headers)


def _criar_conta_com_reuniao_qualificada(client, headers: dict, fake_account_data, cnpj: str) -> dict:
    icp = client.post(
        "/api/v1/icp",
        json={
            "nome": "ICP2", "segmento": "Tecnologia", "porte": "PEQUENO", "regiao": "SP",
            "dores": [], "gatilhos": [], "cnae_codigos": ["6201500"], "ufs": ["SP"],
        },
        headers=headers,
    ).json()
    fake_account_data.candidatos = [
        ContaCandidata(cnpj=cnpj, razao_social="Empresa", cnae_principal="6201500", porte="PEQUENO", uf="SP", situacao_cadastral="ATIVA")
    ]
    conta = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 1}, headers=headers).json()["contas"][0]
    decisor = client.post(
        f"/api/v1/contas/{conta['id']}/decisores",
        json={"nome": "Decisor", "email": "d@empresa.com.br", "telefone": "+5511911112222"},
        headers=headers,
    ).json()

    proposta = client.post(
        f"/api/v1/decisores/{decisor['id']}/reunioes/propor", json={"vendedor_id": "v1"}, headers=headers
    ).json()
    horario = proposta["horarios_propostos"][0]
    confirmada = client.post(
        f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario}, headers=headers
    ).json()
    client.post(f"/api/v1/reunioes/{confirmada['id']}/marcar-resultado", json={"status": "realizada"}, headers=headers)
    client.post(
        f"/api/v1/reunioes/{confirmada['id']}/confirmar-qualificacao",
        json={"qualificada": True, "motivo": None},
        headers=headers,
    )
    return conta


def test_ranking_ordenado_por_atingimento_com_alerta_de_baixo_uso(client, fake_account_data):
    """E8-H3: ranking de assinantes por atingimento com alertas de baixo uso."""
    headers_b = {"X-Tenant-Id": TENANT_B, "X-User-Id": "user-teste"}
    _onboarding(client, headers_b)
    _criar_conta_com_reuniao_qualificada(client, headers_b, fake_account_data, "11111111000101")
    client.put("/api/v1/painel/configuracao-meta", json={"meta_mensal_reunioes": 1}, headers=headers_b)

    client.put("/api/v1/painel/configuracao-meta", json={"meta_mensal_reunioes": 10})  # tenant A, sem reuniões

    ranking = client.get("/api/v1/painel/admin/ranking").json()
    por_tenant = {item["tenant_id"]: item for item in ranking}

    assert por_tenant[TENANT_B]["atingimento"] == 1.0
    assert por_tenant[TENANT_B]["alerta_baixo_uso"] is False
    assert por_tenant[TENANT_A]["atingimento"] == 0.0
    assert por_tenant[TENANT_A]["alerta_baixo_uso"] is True
    # ordenado por atingimento decrescente
    assert ranking.index(por_tenant[TENANT_B]) < ranking.index(por_tenant[TENANT_A])


def test_isolamento_multi_tenant_no_ranking(client, fake_account_data):
    """E8-H3: dados anonimizados entre assinantes (isolamento verificado)."""
    headers_b = {"X-Tenant-Id": TENANT_B, "X-User-Id": "user-teste"}
    _onboarding(client, headers_b)
    conta_b = _criar_conta_com_reuniao_qualificada(client, headers_b, fake_account_data, "22222222000102")

    ranking = client.get("/api/v1/painel/admin/ranking").json()

    campos_esperados = {"tenant_id", "valor_mes_atual", "meta", "atingimento", "alerta_baixo_uso"}
    for item in ranking:
        assert set(item.keys()) == campos_esperados
        # nenhum dado granular do assinante (nome de conta, cnpj etc.) vaza
        assert conta_b["nome"] not in str(item)
