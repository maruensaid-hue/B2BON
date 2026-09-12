from app.models.registro_oportunidade import RegistroOportunidade
from app.models.tenant import Tenant

TENANT_ID = "tenant-teste"
DISTRIBUIDOR_ID = "distribuidor-ro-teste"
CLIENTE_FILHO_ID = "cliente-filho-ro-teste"
OUTRA_REDE_ID = "outra-rede-ro-teste"
CNPJ = "11222333000181"
CNPJ_FORMATADO = "11.222.333/0001-81"


def _criar_tenant(db_session, tenant_id: str, tipo: str = "cliente", tenant_pai_id: str | None = None) -> None:
    if db_session.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        db_session.add(
            Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo, tenant_pai_id=tenant_pai_id)
        )
        db_session.commit()


def _montar_hierarquia(db_session) -> None:
    """distribuidor-ro-teste (raiz) -> cliente-filho-ro-teste; e uma rede
    irmã (outra-rede-ro-teste), sem nenhuma relação, pra garantir que o
    conflito de PRIME não vaza pra fora da rede."""
    _criar_tenant(db_session, DISTRIBUIDOR_ID, tipo="distribuidor")
    _criar_tenant(db_session, CLIENTE_FILHO_ID, tipo="cliente", tenant_pai_id=DISTRIBUIDOR_ID)
    _criar_tenant(db_session, OUTRA_REDE_ID, tipo="cliente")


def test_registro_bem_sucedido_fica_prime(client, db_session, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-ro-1@teste.com.br")

    resposta = client.post(
        "/api/v1/registro-oportunidade",
        json={"cnpj": CNPJ_FORMATADO, "nome_empresa": "Empresa Prospectada"},
        headers=headers,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "ativo"
    assert corpo["cnpj"] == CNPJ
    assert corpo["tenant_id"] == TENANT_ID


def test_segundo_revendedor_da_mesma_rede_e_bloqueado(client, db_session, criar_usuario_autenticado):
    """Raio-X: deal registration — dois revendedores da MESMA rede
    (distribuidor + cliente-filho) não podem registrar a mesma empresa."""
    _montar_hierarquia(db_session)
    headers_pai = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="user", email="vendedor-pai-ro@teste.com.br")
    headers_filho = criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="user", email="vendedor-filho-ro@teste.com.br")

    primeiro = client.post(
        "/api/v1/registro-oportunidade",
        json={"cnpj": CNPJ, "nome_empresa": "Empresa Disputada"},
        headers=headers_pai,
    )
    assert primeiro.status_code == 201

    segundo = client.post(
        "/api/v1/registro-oportunidade",
        json={"cnpj": CNPJ, "nome_empresa": "Empresa Disputada"},
        headers=headers_filho,
    )

    assert segundo.status_code == 409
    ativos = db_session.query(RegistroOportunidade).filter_by(cnpj=CNPJ, status="ativo").all()
    assert len(ativos) == 1
    assert ativos[0].tenant_id == DISTRIBUIDOR_ID


def test_mesmo_cnpj_em_redes_diferentes_nao_conflita(client, db_session, criar_usuario_autenticado):
    """Isolamento preservado: redes sem relação nenhuma podem registrar o
    mesmo CNPJ sem conflito — cada uma é um cliente pagante isolado."""
    _montar_hierarquia(db_session)
    headers_rede_a = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="user", email="vendedor-rede-a@teste.com.br")
    headers_rede_b = criar_usuario_autenticado(OUTRA_REDE_ID, papel="user", email="vendedor-rede-b@teste.com.br")

    resposta_a = client.post(
        "/api/v1/registro-oportunidade", json={"cnpj": CNPJ, "nome_empresa": "Empresa X"}, headers=headers_rede_a
    )
    resposta_b = client.post(
        "/api/v1/registro-oportunidade", json={"cnpj": CNPJ, "nome_empresa": "Empresa X"}, headers=headers_rede_b
    )

    assert resposta_a.status_code == 201
    assert resposta_b.status_code == 201


def test_criar_conta_com_cnpj_linka_automaticamente_ao_ro(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_pai = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="user", email="vendedor-link-ro@teste.com.br")
    headers_filho = criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="admin", email="admin-link-ro@teste.com.br")

    registro = client.post(
        "/api/v1/registro-oportunidade",
        json={"cnpj": CNPJ, "nome_empresa": "Empresa a Cadastrar"},
        headers=headers_pai,
    ).json()
    assert registro["conta_id"] is None

    resposta_conta = client.post(
        "/api/v1/leads/contas",
        json={"nome": "Empresa a Cadastrar", "cnpj": CNPJ_FORMATADO, "dominio": None},
        headers=headers_filho,
    )
    assert resposta_conta.status_code == 201
    conta_id = resposta_conta.json()["id"]

    listagem = client.get("/api/v1/registro-oportunidade", headers=headers_pai).json()
    registro_atualizado = next(r for r in listagem if r["id"] == registro["id"])
    assert registro_atualizado["conta_id"] == conta_id


def test_dono_do_ro_ativo_consegue_solicitar_desconto(client, db_session, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT_ID, papel="user", email="vendedor-ro-desconto@teste.com.br")
    registro = client.post(
        "/api/v1/registro-oportunidade", json={"cnpj": CNPJ, "nome_empresa": "Empresa Desconto"}, headers=headers
    ).json()

    resposta = client.post(
        f"/api/v1/registro-oportunidade/{registro['id']}/solicitar-desconto",
        json={"percentual_solicitado": 15.0, "justificativa": "Negociação avançada"},
        headers=headers,
    )

    assert resposta.status_code == 201
    assert resposta.json()["status"] == "pendente"


def test_quem_nao_e_prime_e_bloqueado_ao_solicitar_desconto(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_pai = criar_usuario_autenticado(DISTRIBUIDOR_ID, papel="user", email="vendedor-prime@teste.com.br")
    headers_filho = criar_usuario_autenticado(CLIENTE_FILHO_ID, papel="user", email="vendedor-nao-prime@teste.com.br")

    registro = client.post(
        "/api/v1/registro-oportunidade", json={"cnpj": CNPJ, "nome_empresa": "Empresa Alheia"}, headers=headers_pai
    ).json()

    resposta = client.post(
        f"/api/v1/registro-oportunidade/{registro['id']}/solicitar-desconto",
        json={"percentual_solicitado": 10.0},
        headers=headers_filho,
    )

    assert resposta.status_code == 409


def test_admin_da_raiz_aprova_e_admin_do_meio_nao_consegue(client, db_session, criar_usuario_autenticado):
    _montar_hierarquia(db_session)
    headers_vendedor = criar_usuario_autenticado(
        CLIENTE_FILHO_ID, papel="user", email="vendedor-aprova-ro@teste.com.br"
    )
    headers_admin_raiz = criar_usuario_autenticado(
        DISTRIBUIDOR_ID, papel="admin", email="admin-raiz-ro@teste.com.br"
    )
    headers_admin_filho = criar_usuario_autenticado(
        CLIENTE_FILHO_ID, papel="admin", email="admin-filho-ro@teste.com.br"
    )

    registro = client.post(
        "/api/v1/registro-oportunidade", json={"cnpj": CNPJ, "nome_empresa": "Empresa Aprovar"},
        headers=headers_vendedor,
    ).json()
    solicitacao = client.post(
        f"/api/v1/registro-oportunidade/{registro['id']}/solicitar-desconto",
        json={"percentual_solicitado": 12.0},
        headers=headers_vendedor,
    ).json()

    resposta_admin_meio = client.put(
        f"/api/v1/registro-oportunidade/solicitacoes-desconto/{solicitacao['id']}",
        json={"aprovar": True},
        headers=headers_admin_filho,
    )
    assert resposta_admin_meio.status_code == 404

    resposta_admin_raiz = client.put(
        f"/api/v1/registro-oportunidade/solicitacoes-desconto/{solicitacao['id']}",
        json={"aprovar": True, "motivo": "Aprovado pelo fabricante"},
        headers=headers_admin_raiz,
    )
    assert resposta_admin_raiz.status_code == 200
    assert resposta_admin_raiz.json()["status"] == "aprovado"
