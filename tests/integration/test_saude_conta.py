from app.models.conta import Conta
from app.models.icp import ICP
from app.models.tenant import Tenant
from app.models.usuario import Usuario

TENANT_ID = "tenant-teste"


def _criar_conta(
    db_session, vendedor_usuario_id: int | None = None, nome: str = "Conta Teste", tenant_id: str = TENANT_ID
) -> Conta:
    icp = db_session.query(ICP).filter_by(tenant_id=tenant_id).first()
    if icp is None:
        icp = ICP(
            tenant_id=tenant_id, grupo_id="grupo-saude-conta", nome="ICP", segmento="Tecnologia",
            porte="PEQUENO", regiao="SP", ativo=True,
        )
        db_session.add(icp)
        db_session.flush()
    conta = Conta(
        tenant_id=tenant_id, icp_id=icp.id, nome=nome, status="prospectada",
        vendedor_usuario_id=vendedor_usuario_id,
    )
    db_session.add(conta)
    db_session.commit()
    return conta


def _id_do_usuario(db_session, email: str) -> int:
    return db_session.query(Usuario).filter_by(email=email).one().id


def _criar_tenant(db_session, tenant_id: str, tipo: str = "cliente", tenant_pai_id: str | None = None) -> None:
    if db_session.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        db_session.add(
            Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo, tenant_pai_id=tenant_pai_id)
        )
        db_session.commit()


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


def test_dashboard_traz_roi_e_cs_score(client, db_session):
    """Raio-X: ROI e CS são métricas que existiam numa versão anterior do
    MAP, antes de integrar à B2B ON — pedido do usuário pra trazer de
    volta. Sem nenhum dado de NPS/economia ainda, os dois vêm None em
    vez de quebrar a rota."""
    _criar_conta(db_session, nome="Conta 1")

    resposta = client.get("/api/v1/saude-contas/dashboard")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "roi" in corpo
    assert "cs_score" in corpo
    assert "nps_medio" in corpo


def test_script_resgate_via_llm(client, db_session, fake_llm):
    conta = _criar_conta(db_session)
    fake_llm.definir_respostas(["Olá! Notei que faz um tempo desde nosso último contato..."])

    resposta = client.get(f"/api/v1/saude-contas/contas/{conta.id}/script-resgate")

    assert resposta.status_code == 200
    assert "Olá" in resposta.json()["script"]


DISTRIBUIDOR_ID = "distribuidor-teste"
CLIENTE_FILHO_ID = "cliente-filho-teste"
OUTRA_ARVORE_ID = "outra-arvore-teste"


def _montar_hierarquia(db_session):
    """distribuidor-teste (raiz) -> cliente-filho-teste; e uma árvore
    irmã (outra-arvore-teste) sem nenhuma relação, pra garantir que o
    escopo não vaza pra fora da subárvore do distribuidor."""
    _criar_tenant(db_session, DISTRIBUIDOR_ID, tipo="distribuidor")
    _criar_tenant(db_session, CLIENTE_FILHO_ID, tipo="cliente", tenant_pai_id=DISTRIBUIDOR_ID)
    _criar_tenant(db_session, OUTRA_ARVORE_ID, tipo="cliente")


def test_admin_de_distribuidor_ve_contas_da_subarvore_sem_filtro(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist@teste.com.br")
    conta_pai = _criar_conta(db_session, nome="Conta do distribuidor", tenant_id=DISTRIBUIDOR_ID)
    conta_filha = _criar_conta(db_session, nome="Conta do cliente filho", tenant_id=CLIENTE_FILHO_ID)
    _criar_conta(db_session, nome="Conta de outra árvore", tenant_id=OUTRA_ARVORE_ID)

    ranking = client.get("/api/v1/saude-contas/ranking", headers=headers_admin).json()

    ids = {item["conta_id"] for item in ranking}
    assert ids == {conta_pai.id, conta_filha.id}
    tenant_ids_no_ranking = {item["tenant_id"] for item in ranking}
    assert tenant_ids_no_ranking == {DISTRIBUIDOR_ID, CLIENTE_FILHO_ID}


def test_admin_de_distribuidor_pode_dar_zoom_num_tenant_da_subarvore(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-2@teste.com.br")
    _criar_conta(db_session, nome="Conta do distribuidor", tenant_id=DISTRIBUIDOR_ID)
    conta_filha = _criar_conta(db_session, nome="Conta do cliente filho", tenant_id=CLIENTE_FILHO_ID)

    ranking = client.get(
        f"/api/v1/saude-contas/ranking?tenant_id_selecionado={CLIENTE_FILHO_ID}", headers=headers_admin
    ).json()

    assert [item["conta_id"] for item in ranking] == [conta_filha.id]


def test_tenant_id_selecionado_fora_do_escopo_e_rejeitado(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-3@teste.com.br")

    resposta = client.get(
        f"/api/v1/saude-contas/ranking?tenant_id_selecionado={OUTRA_ARVORE_ID}", headers=headers_admin
    )

    assert resposta.status_code == 403


def test_admin_de_tenant_cliente_sem_subarvore_nao_muda_de_comportamento(client, db_session, criar_usuario_autenticado):
    """Regressão: a maioria dos admins não gerencia hierarquia nenhuma —
    continuam vendo só o próprio tenant, exatamente como antes."""
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-cliente@teste.com.br")
    conta = _criar_conta(db_session, nome="Conta própria")

    ranking = client.get("/api/v1/saude-contas/ranking", headers=headers_admin).json()

    assert [item["conta_id"] for item in ranking] == [conta.id]


def test_admin_de_distribuidor_abre_detalhe_de_conta_do_subtenant(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-4@teste.com.br")
    conta_filha = _criar_conta(db_session, nome="Conta do cliente filho", tenant_id=CLIENTE_FILHO_ID)

    resposta_score = client.get(f"/api/v1/saude-contas/contas/{conta_filha.id}/score-risco", headers=headers_admin)
    assert resposta_score.status_code == 200

    resposta_interacao = client.post(
        "/api/v1/saude-contas/interacoes",
        json={"conta_id": conta_filha.id, "tipo": "contato"},
        headers=headers_admin,
    )
    assert resposta_interacao.status_code == 201

    resposta_interacoes = client.get(
        f"/api/v1/saude-contas/contas/{conta_filha.id}/interacoes", headers=headers_admin
    )
    assert resposta_interacoes.status_code == 200
    assert len(resposta_interacoes.json()) == 1


def test_atribuir_vendedor_busca_vendedor_no_tenant_da_conta(client, db_session, criar_usuario_autenticado):
    """O vendedor mora no tenant da conta (o filho), não no do admin que
    está chamando (o distribuidor, pai) — raio-X 2026-09-10."""
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-5@teste.com.br")
    criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="user", email="vendedor-filho@teste.com.br")
    vendedor_id = _id_do_usuario(db_session, "vendedor-filho@teste.com.br")
    conta_filha = _criar_conta(db_session, nome="Conta do cliente filho", tenant_id=CLIENTE_FILHO_ID)

    resposta = client.put(
        f"/api/v1/saude-contas/contas/{conta_filha.id}/vendedor",
        json={"vendedor_usuario_id": vendedor_id},
        headers=headers_admin,
    )

    assert resposta.status_code == 200
    assert resposta.json()["vendedor_usuario_id"] == vendedor_id


def test_vendedores_disponiveis_lista_vendedor_do_subtenant(client, db_session, criar_usuario_autenticado):
    """Raio-X 2026-09-11: o campo "Vendedor responsável" usava
    `GET /usuarios` (só o próprio tenant de quem chama) — um admin de
    distribuidor via a conta de um sub-tenant pela hierarquia, mas o
    vendedor de lá nunca aparecia pra ser atribuído."""
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-6@teste.com.br")
    criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="user", email="vendedor-filho-2@teste.com.br")
    conta_filha = _criar_conta(db_session, nome="Conta do cliente filho", tenant_id=CLIENTE_FILHO_ID)

    resposta = client.get(
        f"/api/v1/saude-contas/contas/{conta_filha.id}/vendedores-disponiveis", headers=headers_admin
    )

    assert resposta.status_code == 200
    emails = {u["email"] for u in resposta.json()}
    assert "vendedor-filho-2@teste.com.br" in emails


def test_vendedores_disponiveis_inclui_toda_a_subarvore_mas_nao_extravasa(
    client, db_session, criar_usuario_autenticado
):
    """Raio-X 2026-09-11 (3a rodada): pra este uso da hierarquia, os
    sub-tenants são estrutura interna do próprio time do Admin
    (matriz/filial), não clientes pagantes separados — então o vendedor
    do tenant PAI (distribuidor) TAMBÉM deve poder ser atribuído numa
    conta do tenant FILHO (e vice-versa). O limite continua sendo a
    subárvore: um vendedor de uma árvore de tenants sem nenhuma relação
    (`outra-arvore-teste`) não pode aparecer."""
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-7@teste.com.br")
    criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="user", email="vendedor-do-pai@teste.com.br")
    criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="user", email="vendedor-do-filho@teste.com.br")
    criar_usuario_autenticado(OUTRA_ARVORE_ID, papel="user", email="vendedor-de-outra-arvore@teste.com.br")
    conta_filha = _criar_conta(db_session, nome="Conta do cliente filho", tenant_id=CLIENTE_FILHO_ID)

    resposta = client.get(
        f"/api/v1/saude-contas/contas/{conta_filha.id}/vendedores-disponiveis", headers=headers_admin
    )

    emails = {u["email"] for u in resposta.json()}
    assert "vendedor-do-filho@teste.com.br" in emails
    assert "vendedor-do-pai@teste.com.br" in emails
    assert "vendedor-de-outra-arvore@teste.com.br" not in emails


def test_atribuir_vendedor_do_subtenant_a_conta_do_tenant_pai(client, db_session, criar_usuario_autenticado):
    """Cenário real relatado pelo cliente: a empresa (conta) foi
    cadastrada no tenant do próprio Admin (o distribuidor/pai), e o
    vendedor que deveria assumi-la mora num sub-tenant (o cliente/filho)
    — antes disso falhava tanto na listagem quanto na atribuição."""
    _montar_hierarquia(db_session)
    headers_admin = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="admin", email="admin-dist-8@teste.com.br")
    criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="user", email="vendedor-filho-3@teste.com.br")
    vendedor_id = _id_do_usuario(db_session, "vendedor-filho-3@teste.com.br")
    conta_pai = _criar_conta(db_session, nome="Empresa cadastrada pelo Admin", tenant_id=DISTRIBUIDOR_ID)

    resposta_lista = client.get(
        f"/api/v1/saude-contas/contas/{conta_pai.id}/vendedores-disponiveis", headers=headers_admin
    )
    assert resposta_lista.status_code == 200
    emails = {u["email"] for u in resposta_lista.json()}
    assert "vendedor-filho-3@teste.com.br" in emails

    resposta_put = client.put(
        f"/api/v1/saude-contas/contas/{conta_pai.id}/vendedor",
        json={"vendedor_usuario_id": vendedor_id},
        headers=headers_admin,
    )
    assert resposta_put.status_code == 200
    assert resposta_put.json()["vendedor_usuario_id"] == vendedor_id


def test_vendedores_disponiveis_bloqueado_para_user(client, db_session, criar_usuario_autenticado):
    conta = _criar_conta(db_session, nome="Conta Qualquer")
    headers_vendedor = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-comum@teste.com.br")

    resposta = client.get(
        f"/api/v1/saude-contas/contas/{conta.id}/vendedores-disponiveis", headers=headers_vendedor
    )

    assert resposta.status_code == 403


def test_vendedores_disponiveis_admin_comum_ve_o_proprio_tenant(client, db_session, criar_usuario_autenticado):
    """Regressão: sem nenhuma hierarquia envolvida, continua idêntico a
    `GET /usuarios` — mesmo tenant do admin, só ativos."""
    conta = _criar_conta(db_session, nome="Conta Qualquer")
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-comum@teste.com.br")
    criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-comum-2@teste.com.br")

    resposta = client.get(
        f"/api/v1/saude-contas/contas/{conta.id}/vendedores-disponiveis", headers=headers_admin
    )

    assert resposta.status_code == 200
    emails = {u["email"] for u in resposta.json()}
    assert "vendedor-comum-2@teste.com.br" in emails
