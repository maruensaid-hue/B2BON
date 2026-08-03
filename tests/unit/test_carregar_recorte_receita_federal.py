from app.models.icp import ICP
from scripts.carregar_recorte_receita_federal import _unir_filtros_icps_ativos

TENANT_ID = "tenant-recorte"


def _criar_icp(db_session, ativo: bool, cnae_codigos: list[str], ufs: list[str]) -> ICP:
    icp = ICP(
        tenant_id=TENANT_ID,
        grupo_id="grupo-1",
        nome="ICP Teste",
        ativo=ativo,
        segmento="Tecnologia",
        porte="PEQUENO",
        regiao="SP",
        cnae_codigos=cnae_codigos,
        ufs=ufs,
    )
    db_session.add(icp)
    db_session.commit()
    return icp


def test_uniao_de_multiplos_icps_ativos_sem_duplicatas(db_session):
    _criar_icp(db_session, ativo=True, cnae_codigos=["6201500", "6202300"], ufs=["SP"])
    _criar_icp(db_session, ativo=True, cnae_codigos=["6202300", "6203100"], ufs=["SP", "RJ"])

    cnae_codigos, ufs = _unir_filtros_icps_ativos(db_session, TENANT_ID)

    assert cnae_codigos == ["6201500", "6202300", "6203100"]
    assert ufs == ["RJ", "SP"]


def test_icp_inativo_nao_entra_na_uniao(db_session):
    _criar_icp(db_session, ativo=True, cnae_codigos=["6201500"], ufs=["SP"])
    _criar_icp(db_session, ativo=False, cnae_codigos=["9999999"], ufs=["AM"])

    cnae_codigos, ufs = _unir_filtros_icps_ativos(db_session, TENANT_ID)

    assert cnae_codigos == ["6201500"]
    assert ufs == ["SP"]


def test_tenant_sem_icp_retorna_listas_vazias(db_session):
    cnae_codigos, ufs = _unir_filtros_icps_ativos(db_session, "tenant-sem-icp")

    assert cnae_codigos == []
    assert ufs == []
