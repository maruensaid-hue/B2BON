from app.models.icp import ICP
from app.models.perfil_empresa import PerfilEmpresa
from app.services import sinal_oportunidade_service
from app.services.errors import NaoEncontrado

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro"


def _criar_icp(db_session, tenant_id, **overrides) -> ICP:
    dados = {
        "tenant_id": tenant_id,
        "grupo_id": tenant_id,
        "nome": "Healthcare Enterprise",
        "segmento": "healthcare",
        "porte": "grande",
        "regiao": "sudeste",
        "cnae_codigos": ["8610-1/01"],
        "ufs": ["SP", "RJ"],
    }
    dados.update(overrides)
    icp = ICP(**dados)
    db_session.add(icp)
    db_session.commit()
    return icp


def _criar_perfil(db_session, tenant_id, **overrides) -> PerfilEmpresa:
    dados = {"tenant_id": tenant_id, "nome_exibicao": f"Empresa {tenant_id}"}
    dados.update(overrides)
    perfil = PerfilEmpresa(**dados)
    db_session.add(perfil)
    db_session.commit()
    return perfil


def test_fit_total_quando_todos_criterios_batem(db_session):
    icp = _criar_icp(db_session, TENANT_A)
    perfil = _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")

    resultado = sinal_oportunidade_service.calcular_fit_icp(icp, perfil)

    assert resultado["fit_score"] == 1.0
    assert resultado["confidence"] == "alta"
    assert resultado["missing_data"] == []
    assert len(resultado["reasons"]) == 3


def test_fit_parcial_e_dados_faltantes(db_session):
    icp = _criar_icp(db_session, TENANT_A)
    perfil = _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01")  # sem sede_uf/porte

    resultado = sinal_oportunidade_service.calcular_fit_icp(icp, perfil)

    assert resultado["fit_score"] == 0.5
    assert set(resultado["missing_data"]) == {"sede_uf", "porte"}
    assert resultado["confidence"] == "baixa"


def test_fit_zero_quando_nada_bate(db_session):
    icp = _criar_icp(db_session, TENANT_A)
    perfil = _criar_perfil(db_session, TENANT_B, cnae_principal="4711-3/02", sede_uf="BA", porte="pequeno")

    resultado = sinal_oportunidade_service.calcular_fit_icp(icp, perfil)

    assert resultado["fit_score"] == 0.0
    assert resultado["reasons"] == []
    assert resultado["confidence"] == "alta"  # todo dado presente, só não bateu nenhum critério


def test_listar_fit_icp_rede_ordena_por_score_desc(db_session):
    icp = _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="4711-3/02", sede_uf="BA", porte="pequeno")
    _criar_perfil(db_session, TENANT_C, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")

    resultados = sinal_oportunidade_service.listar_fit_icp_rede(db_session, TENANT_A, icp.id)

    assert [r["tenant_id_candidato"] for r in resultados] == [TENANT_C, TENANT_B]
    assert resultados[0]["fit_score"] == 1.0
    assert resultados[1]["fit_score"] == 0.0


def test_listar_fit_icp_rede_exclui_proprio_tenant(db_session):
    icp = _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_A, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")

    resultados = sinal_oportunidade_service.listar_fit_icp_rede(db_session, TENANT_A, icp.id)

    assert resultados == []


def test_listar_fit_icp_rede_icp_inexistente_levanta_erro(db_session):
    try:
        sinal_oportunidade_service.listar_fit_icp_rede(db_session, TENANT_A, 9999)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_listar_fit_icp_rede_icp_de_outro_tenant_levanta_erro(db_session):
    icp = _criar_icp(db_session, TENANT_A)

    try:
        sinal_oportunidade_service.listar_fit_icp_rede(db_session, TENANT_B, icp.id)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
