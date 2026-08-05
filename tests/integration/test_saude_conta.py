from app.models.conta import Conta
from app.models.icp import ICP
from app.models.usuario import Usuario

TENANT_ID = "tenant-teste"


def _criar_conta(db_session, vendedor_usuario_id: int | None = None, nome: str = "Conta Teste") -> Conta:
    icp = db_session.query(ICP).filter_by(tenant_id=TENANT_ID).first()
    if icp is None:
        icp = ICP(
            tenant_id=TENANT_ID, grupo_id="grupo-saude-conta", nome="ICP", segmento="Tecnologia",
            porte="PEQUENO", regiao="SP", ativo=True,
        )
        db_session.add(icp)
        db_session.flush()
    conta = Conta(
        tenant_id=TENANT_ID, icp_id=icp.id, nome=nome, status="prospectada",
        vendedor_usuario_id=vendedor_usuario_id,
    )
    db_session.add(conta)
    db_session.commit()
    return conta


def _id_do_usuario(db_session, email: str) -> int:
    return db_session.query(Usuario).filter_by(email=email).one().id


def test_registrar_interacao_e_calcular_score(client, db_session):
    conta = _criar_conta(db_session)

    resposta = client.post(
        "/api/v1/saude-contas/interacoes", json={"conta_id": conta.id, "tipo": "reclamacao"}
    )
    assert resposta.status_code == 201

    score = client.get(f"/api/v1/saude-contas/contas/{conta.id}/score-risco").json()
    assert score["sinais"]["reclamacoes"] == 15
    assert score["classificacao"] in {"atencao", "critico", "saudavel"}


def test_tipo_invalido_e_rejeitado(client, db_session):
    conta = _criar_conta(db_session)

    resposta = client.post(
        "/api/v1/saude-contas/interacoes", json={"conta_id": conta.id, "tipo": "chute-invalido"}
    )
    assert resposta.status_code == 422


def test_user_so_ve_contas_das_quais_e_o_vendedor(client, db_session, criar_usuario_autenticado):
    """Bug de escopo: vendedor não pode enxergar a carteira dos colegas."""
    headers_vendedor_a = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-a@teste.com.br")
    headers_vendedor_b = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-b@teste.com.br")
    vendedor_a_id = _id_do_usuario(db_session, "vendedor-a@teste.com.br")

    conta_a = _criar_conta(db_session, vendedor_usuario_id=vendedor_a_id, nome="Conta do Vendedor A")
    _criar_conta(db_session, vendedor_usuario_id=None, nome="Conta sem vendedor")

    ranking_a = client.get("/api/v1/saude-contas/ranking", headers=headers_vendedor_a).json()
    assert [item["conta_id"] for item in ranking_a] == [conta_a.id]

    ranking_b = client.get("/api/v1/saude-contas/ranking", headers=headers_vendedor_b).json()
    assert ranking_b == []


def test_admin_ve_todas_as_contas_e_pode_filtrar_por_vendedor(client, db_session, criar_usuario_autenticado):
    headers_vendedor = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-c@teste.com.br")
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="gestor@teste.com.br")
    vendedor_id = _id_do_usuario(db_session, "vendedor-c@teste.com.br")

    conta_do_vendedor = _criar_conta(db_session, vendedor_usuario_id=vendedor_id, nome="Conta atribuída")
    _criar_conta(db_session, vendedor_usuario_id=None, nome="Conta sem dono")

    ranking_completo = client.get("/api/v1/saude-contas/ranking", headers=headers_admin).json()
    assert len(ranking_completo) == 2

    ranking_filtrado = client.get(
        f"/api/v1/saude-contas/ranking?vendedor_usuario_id={vendedor_id}", headers=headers_admin
    ).json()
    assert [item["conta_id"] for item in ranking_filtrado] == [conta_do_vendedor.id]


def test_atribuir_vendedor_bloqueado_para_user(client, db_session, criar_usuario_autenticado):
    conta = _criar_conta(db_session)
    headers_vendedor = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-d@teste.com.br")

    resposta = client.put(
        f"/api/v1/saude-contas/contas/{conta.id}/vendedor",
        json={"vendedor_usuario_id": None},
        headers=headers_vendedor,
    )

    assert resposta.status_code == 403


def test_admin_atribui_vendedor_a_conta(client, db_session, criar_usuario_autenticado):
    conta = _criar_conta(db_session)
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="gestor-2@teste.com.br")
    criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-e@teste.com.br")
    vendedor_id = _id_do_usuario(db_session, "vendedor-e@teste.com.br")

    resposta = client.put(
        f"/api/v1/saude-contas/contas/{conta.id}/vendedor",
        json={"vendedor_usuario_id": vendedor_id},
        headers=headers_admin,
    )

    assert resposta.status_code == 200
    assert resposta.json()["vendedor_usuario_id"] == vendedor_id


def test_dashboard_agrega_contas_visiveis(client, db_session):
    _criar_conta(db_session, nome="Conta 1")
    _criar_conta(db_session, nome="Conta 2")

    resposta = client.get("/api/v1/saude-contas/dashboard")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total_contas"] == 2


def test_script_resgate_via_llm(client, db_session, fake_llm):
    conta = _criar_conta(db_session)
    fake_llm.definir_respostas(["Olá! Notei que faz um tempo desde nosso último contato..."])

    resposta = client.get(f"/api/v1/saude-contas/contas/{conta.id}/script-resgate")

    assert resposta.status_code == 200
    assert "Olá" in resposta.json()["script"]
