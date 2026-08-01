TENANT_ID = "tenant-teste"


def _propor_e_confirmar(client, decisor_id: int) -> dict:
    reuniao = client.post(
        f"/api/v1/decisores/{decisor_id}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = reuniao["horarios_propostos"][0]
    return client.post(f"/api/v1/reunioes/{reuniao['id']}/confirmar", json={"horario_escolhido": horario}).json()


def test_dossie_tem_dores_score_historico_e_proxima_acao(client, criar_conta_com_decisor, fake_llm):
    """E7-H1: dossiê com dores, respostas, score decomposto, histórico e próxima ação."""
    conta, decisor = criar_conta_com_decisor()
    fake_llm.definir_respostas(["CONTINUAR: pergunta"])
    client.post(
        "/api/v1/webhooks/whatsapp",
        json={"tenant_id": TENANT_ID, "telefone": decisor.telefone, "texto": "minha dor é falta de processo"},
    )

    confirmada = _propor_e_confirmar(client, decisor.id)

    dossie = client.get(f"/api/v1/reunioes/{confirmada['id']}/dossie")

    assert dossie.status_code == 200
    corpo = dossie.json()
    assert corpo["dores"] == ["minha dor é falta de processo"]
    assert corpo["score_total"] is not None
    assert corpo["score_criterios"]["dores"] == 20.0
    assert corpo["proxima_acao_recomendada"]


def test_dossie_anexado_ao_crm(client, criar_conta_com_decisor, fake_crm):
    """E7-H1: dossiê anexado automaticamente à oportunidade no CRM."""
    conta, decisor = criar_conta_com_decisor()
    confirmada = _propor_e_confirmar(client, decisor.id)

    client.get(f"/api/v1/reunioes/{confirmada['id']}/dossie")

    assert len(fake_crm.notas) == 1
    assert fake_crm.notas[0]["oportunidade_id"] == confirmada["origem_crm_id"]


def test_devolucao_reinsere_em_cadencia_de_nutricao(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia_nutricao
):
    """E7-H2: devolução reinsere o lead em cadência de nutrição adequada ao motivo."""
    conta, decisor = criar_conta_com_decisor()
    nutricao = criar_cadencia_nutricao()

    resposta = client.post(
        f"/api/v1/decisores/{decisor.id}/devolver",
        json={"motivo": "sem fit agora", "cadencia_nutricao_id": nutricao["id"]},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["cadencia_nutricao_id"] == nutricao["id"]
    assert corpo["mensagens_geradas"] == 5


def test_devolucao_nao_duplica_mensagens_pendentes(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, criar_cadencia_nutricao
):
    """E7-H2: histórico preservado; lead não recebe mensagens redundantes."""
    conta, decisor = criar_conta_com_decisor()
    prospeccao = criar_cadencia()
    client.post(f"/api/v1/cadencias/{prospeccao['id']}/gerar", json={"conta_ids": [conta.id]})

    nutricao = criar_cadencia_nutricao()
    resposta = client.post(
        f"/api/v1/decisores/{decisor.id}/devolver",
        json={"motivo": "esfriou", "cadencia_nutricao_id": nutricao["id"]},
    ).json()

    # os 5 toques pendentes da prospecção foram cancelados, não somados aos novos
    assert resposta["mensagens_canceladas"] == 5
    assert resposta["mensagens_geradas"] == 5


def test_devolver_exige_cadencia_de_tipo_nutricao(client, onboarding_completo, criar_conta_com_decisor, criar_cadencia):
    conta, decisor = criar_conta_com_decisor()
    prospeccao = criar_cadencia()  # tipo="prospeccao" por padrão

    resposta = client.post(
        f"/api/v1/decisores/{decisor.id}/devolver",
        json={"motivo": "esfriou", "cadencia_nutricao_id": prospeccao["id"]},
    )

    assert resposta.status_code == 404
