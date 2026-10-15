"""Regressões de autorização por atribuição explícita de oportunidades."""

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.usuario import Usuario
from app.services import crm_service

TENANT_ID = "tenant-teste"


def _criar_oportunidade(db_session, conta, decisor, vendedor_usuario_id=None):
    estagio = crm_service.garantir_estagios_padrao(db_session, TENANT_ID)[0]
    negocio = Negocio(
        tenant_id=TENANT_ID,
        conta_id=conta.id,
        decisor_id=decisor.id,
        vendedor_usuario_id=vendedor_usuario_id,
        nome="Oportunidade de teste de autorização",
        valor=1200.0,
        probabilidade=50,
        estagio_id=estagio.id,
        origem="manual",
    )
    db_session.add(negocio)
    db_session.commit()
    db_session.refresh(negocio)
    return negocio


def test_oportunidade_sem_atribuicao_fica_oculta_ate_para_criador_da_empresa(
    client, db_session, criar_usuario_autenticado
):
    headers = criar_usuario_autenticado(
        TENANT_ID, papel="user", email="vendedor-oportunidade-sem-atribuicao@teste.com.br"
    )
    vendedor = db_session.query(Usuario).filter_by(
        email="vendedor-oportunidade-sem-atribuicao@teste.com.br"
    ).one()
    conta = Conta(
        tenant_id=TENANT_ID,
        nome="Empresa criada pelo representante",
        status="priorizada",
        vendedor_usuario_id=vendedor.id,
        criado_por_usuario_id=vendedor.id,
    )
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Contato da empresa")
    db_session.add(decisor)
    db_session.commit()
    negocio = _criar_oportunidade(db_session, conta, decisor)

    listagem = client.get("/api/v1/crm/negocios", headers=headers)
    assert listagem.status_code == 200
    assert negocio.id not in {item["id"] for item in listagem.json()}

    acesso_direto = client.put(
        f"/api/v1/crm/negocios/{negocio.id}",
        headers=headers,
        json={
            "nome": "Tentativa de acesso por ID",
            "valor": 1200.0,
            "probabilidade": 50,
            "decisor_id": decisor.id,
        },
    )
    assert acesso_direto.status_code == 404


def test_admin_pode_atribuir_oportunidade_e_representante_passa_a_visualiza_la(
    client, db_session, criar_conta_com_decisor, criar_usuario_autenticado
):
    conta, decisor = criar_conta_com_decisor()
    negocio = _criar_oportunidade(db_session, conta, decisor)
    headers_vendedor = criar_usuario_autenticado(
        TENANT_ID, papel="user", email="vendedor-atribuicao-explicita@teste.com.br"
    )
    vendedor = db_session.query(Usuario).filter_by(
        email="vendedor-atribuicao-explicita@teste.com.br"
    ).one()

    antes = client.get("/api/v1/crm/negocios", headers=headers_vendedor)
    assert antes.status_code == 200
    assert negocio.id not in {item["id"] for item in antes.json()}

    atribuicao = client.put(
        f"/api/v1/crm/negocios/{negocio.id}/vendedor",
        json={"vendedor_usuario_id": vendedor.id},
    )
    assert atribuicao.status_code == 200
    assert atribuicao.json()["vendedor_usuario_id"] == vendedor.id

    depois = client.get("/api/v1/crm/negocios", headers=headers_vendedor)
    assert depois.status_code == 200
    assert negocio.id in {item["id"] for item in depois.json()}


def test_representante_nao_pode_atribuir_oportunidade_nem_escolher_outro_vendedor(
    client, db_session, criar_conta_com_decisor, criar_usuario_autenticado
):
    conta, decisor = criar_conta_com_decisor()
    negocio = _criar_oportunidade(db_session, conta, decisor)
    headers_vendedor = criar_usuario_autenticado(
        TENANT_ID, papel="user", email="vendedor-sem-permissao-atribuicao@teste.com.br"
    )
    vendedor = db_session.query(Usuario).filter_by(
        email="vendedor-sem-permissao-atribuicao@teste.com.br"
    ).one()

    resposta = client.put(
        f"/api/v1/crm/negocios/{negocio.id}/vendedor",
        headers=headers_vendedor,
        json={"vendedor_usuario_id": vendedor.id},
    )
    assert resposta.status_code == 403

    db_session.refresh(negocio)
    assert negocio.vendedor_usuario_id is None
