from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.negocio import Negocio
from app.models.plano import Plano
from app.models.licenca import Licenca
from app.models.proposta_negocio import PropostaNegocio
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import busca_service, crm_service, proposta_service

TENANT_ID = "tenant-busca"
OUTRO_TENANT_ID = "tenant-busca-outro"


def _criar_tenant_e_usuario(db_session, tenant_id: str, papel: str = "user", tipo_tenant: str = "cliente") -> Usuario:
    plano = Plano(nome=f"Plano {tenant_id}", franquia_contas_mes=500, max_usuarios=20, preco_mensal=100.0)
    db_session.add(plano)
    db_session.flush()
    db_session.add(Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo_tenant))
    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    usuario = Usuario(tenant_id=tenant_id, nome="Usuário Teste", email=f"user@{tenant_id}.com.br", papel=papel, ativo=True)
    db_session.add(usuario)
    db_session.commit()
    return usuario


def _criar_conta(db_session, tenant_id: str, **overrides) -> Conta:
    icp = ICP(
        tenant_id=tenant_id, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()
    dados = {"tenant_id": tenant_id, "icp_id": icp.id, "nome": "Conta Teste", "status": "prospectada"}
    dados.update(overrides)
    conta = Conta(**dados)
    db_session.add(conta)
    db_session.commit()
    return conta


def _criar_negocio(db_session, tenant_id: str, conta: Conta, nome: str) -> Negocio:
    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.commit()
    return crm_service.criar_negocio(db_session, tenant_id, "1", conta.id, decisor.id, nome, valor=1000.0)


def test_acha_conta_por_nome(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    _criar_conta(db_session, TENANT_ID, nome="Fábrica de Parafusos Ltda")

    resultados = busca_service.buscar(db_session, usuario, "parafuso")

    assert any(r.tipo == "conta" and "Parafusos" in r.titulo for r in resultados)


def test_acha_conta_por_cnpj(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    _criar_conta(db_session, TENANT_ID, nome="Empresa X", cnpj="12.345.678/0001-99")

    resultados = busca_service.buscar(db_session, usuario, "12.345.678")

    assert any(r.tipo == "conta" for r in resultados)


def test_acha_negocio_pelo_nome_do_cliente(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    conta = _criar_conta(db_session, TENANT_ID, nome="Cliente Acme")
    _criar_negocio(db_session, TENANT_ID, conta, "Licenciamento anual")

    resultados = busca_service.buscar(db_session, usuario, "Acme")

    negocios = [r for r in resultados if r.tipo == "negocio"]
    assert len(negocios) == 1
    assert negocios[0].subtitulo == "Cliente Acme"


def test_acha_proposta_por_numero(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    conta = _criar_conta(db_session, TENANT_ID)
    negocio = _criar_negocio(db_session, TENANT_ID, conta, "Negócio")
    proposta_service.anexar(db_session, TENANT_ID, "1", negocio.id, "p.pdf", "application/pdf", b"x")

    resultados = busca_service.buscar(db_session, usuario, "1")

    propostas = [r for r in resultados if r.tipo == "proposta"]
    assert any(p.titulo == "Proposta #1" for p in propostas)


def test_acha_proposta_por_nome(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    conta = _criar_conta(db_session, TENANT_ID)
    negocio = _criar_negocio(db_session, TENANT_ID, conta, "Negócio")
    proposta_service.anexar(
        db_session, TENANT_ID, "1", negocio.id, "p.pdf", "application/pdf", b"x", nome="Proposta Especial Verão"
    )

    resultados = busca_service.buscar(db_session, usuario, "Especial Verão")

    assert any(r.tipo == "proposta" and r.titulo == "Proposta Especial Verão" for r in resultados)


def test_acha_cadencia_por_nome(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    db_session.add(Cadencia(tenant_id=TENANT_ID, nome="Cadência de Reativação", canais=["email"], status="rascunho"))
    db_session.commit()

    resultados = busca_service.buscar(db_session, usuario, "Reativação")

    assert any(r.tipo == "cadencia" for r in resultados)


def test_isolamento_por_tenant_nao_acha_dado_de_outro_tenant(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    _criar_tenant_e_usuario(db_session, OUTRO_TENANT_ID)
    _criar_conta(db_session, OUTRO_TENANT_ID, nome="Conta Do Outro Tenant Unica")

    resultados = busca_service.buscar(db_session, usuario, "Outro Tenant Unica")

    assert resultados == []


def test_termo_curto_devolve_vazio(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID)
    _criar_conta(db_session, TENANT_ID, nome="A")

    assert busca_service.buscar(db_session, usuario, "a") == []


def test_super_admin_ve_resultado_de_tenant(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID, papel="super_admin")
    db_session.add(Tenant(id="tenant-alvo-busca", razao_social="Tenant Alvo Da Busca"))
    db_session.commit()

    resultados = busca_service.buscar(db_session, usuario, "Alvo Da Busca")

    assert any(r.tipo == "tenant" for r in resultados)


def test_usuario_comum_nao_ve_resultado_de_tenant(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID, papel="user")
    db_session.add(Tenant(id="tenant-alvo-busca-2", razao_social="Tenant Alvo Da Busca Dois"))
    db_session.commit()

    resultados = busca_service.buscar(db_session, usuario, "Alvo Da Busca Dois")

    assert not any(r.tipo == "tenant" for r in resultados)


def test_admin_de_tenant_cliente_nao_ve_resultado_de_tenant(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID, papel="admin", tipo_tenant="cliente")
    db_session.add(Tenant(id="tenant-alvo-busca-3", razao_social="Tenant Alvo Da Busca Tres"))
    db_session.commit()

    resultados = busca_service.buscar(db_session, usuario, "Alvo Da Busca Tres")

    assert not any(r.tipo == "tenant" for r in resultados)


def test_admin_de_tenant_distribuidor_ve_resultado_de_tenant(db_session):
    usuario = _criar_tenant_e_usuario(db_session, TENANT_ID, papel="admin", tipo_tenant="distribuidor")
    db_session.add(Tenant(id="tenant-alvo-busca-4", razao_social="Tenant Alvo Da Busca Quatro", tenant_pai_id=TENANT_ID))
    db_session.commit()

    resultados = busca_service.buscar(db_session, usuario, "Alvo Da Busca Quatro")

    assert any(r.tipo == "tenant" for r in resultados)
