from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.services import ropa_service

TENANT_ID = "tenant-teste"


def _criar_icp_e_conta(db_session):
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()

    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome="Conta Teste", status="prospectada", origem="receita_federal_cnpj")
    db_session.add(conta)
    db_session.commit()
    return icp, conta


def test_ropa_tenant_nao_declara_dados_pessoais_sem_decisor(db_session):
    """Minimização: sem decisor mapeado, o ROPA do tenant não declara campos
    pessoais de decisor — o motor não coletou o que não precisava."""
    _criar_icp_e_conta(db_session)

    ropa = ropa_service.gerar_ropa_tenant(db_session, TENANT_ID)

    assert "cargo" not in ropa["dados_tratados"]
    assert "email" not in ropa["dados_tratados"]
    assert "nome" in ropa["dados_tratados"]  # campo de Conta


def test_ropa_tenant_reflete_icp_fontes_e_canais(db_session):
    icp, conta = _criar_icp_e_conta(db_session)
    db_session.add(Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor", cargo="Sócio"))
    db_session.commit()

    ropa = ropa_service.gerar_ropa_tenant(db_session, TENANT_ID)

    assert ropa["icp_ids"] == [icp.id]
    assert "receita_federal_cnpj" in ropa["fontes_dados"]
    assert "cargo" in ropa["dados_tratados"]  # agora há decisor, entra na declaração
    assert ropa["canais_ativos"] == []  # E3 (canais) não existe nesta onda
    assert ropa["base_legal"] == "legitimo_interesse"


def test_minimizacao_conforme_por_construcao(db_session):
    """E9-H1: minimização verificada — nenhuma coluna de dado real de
    Conta/Decisor fica fora do que o ROPA (plataforma + tenant) declara."""
    _, conta = _criar_icp_e_conta(db_session)
    db_session.add(Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor"))
    db_session.commit()

    resultado = ropa_service.verificar_minimizacao(db_session, TENANT_ID)

    assert resultado == {"conforme": True, "divergencias": []}
