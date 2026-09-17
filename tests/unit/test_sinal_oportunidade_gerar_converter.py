from app.models.conta import Conta
from app.models.icp import ICP
from app.models.perfil_empresa import PerfilEmpresa
from app.services import intent_service, relacionamento_empresarial_service, sinal_oportunidade_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

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
        "ufs": ["SP"],
        "ativo": True,
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


def test_gerar_sinais_por_fit_icp(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")

    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    assert len(sinais) == 1
    assert sinais[0]["tenant_id_alvo"] == TENANT_B
    assert sinais[0]["tipo_sinal"] == "fit_icp"
    assert sinais[0]["status"] == "novo"


def test_gerar_sinais_por_match_intent(db_session):
    intent_service.criar(
        db_session, TENANT_A, None, "backup", "Backup imutavel", "Precisamos de backup imutavel.",
        ["imutabilidade"], None, None, None, None, "publica",
    )
    _criar_perfil(db_session, TENANT_B, produtos_servicos=["backup imutavel"])

    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    assert len(sinais) == 1
    assert sinais[0]["tipo_sinal"] == "match_intent"


def test_gerar_sinais_por_relacionamento_declarado(db_session):
    _criar_perfil(db_session, TENANT_B)
    relacionamento_empresarial_service.declarar(db_session, TENANT_B, None, TENANT_A, "LOOKING_FOR", "publica")

    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    assert len(sinais) == 1
    assert sinais[0]["tenant_id_alvo"] == TENANT_B
    assert sinais[0]["tipo_sinal"] == "relacionamento_declarado"


def test_gerar_sinais_e_idempotente_atualiza_em_vez_de_duplicar(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")

    sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    assert len(sinais) == 1


def test_gerar_sinais_nao_sobrescreve_sinal_descartado(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)
    sinal_oportunidade_service.descartar(db_session, TENANT_A, None, sinais[0]["id"])

    sinais_regerados = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    assert sinais_regerados[0]["status"] == "descartado"


def test_marcar_visto_so_atualiza_status_novo(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    visto = sinal_oportunidade_service.marcar_visto(db_session, TENANT_A, sinais[0]["id"])

    assert visto["status"] == "visto"


def test_descartar_sinal_ja_convertido_levanta_erro(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)
    sinal_oportunidade_service.converter_em_oportunidade(db_session, TENANT_A, None, sinais[0]["id"])

    try:
        sinal_oportunidade_service.descartar(db_session, TENANT_A, None, sinais[0]["id"])
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_converter_em_oportunidade_cria_conta_e_marca_convertido(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    resultado = sinal_oportunidade_service.converter_em_oportunidade(db_session, TENANT_A, None, sinais[0]["id"])

    conta = db_session.query(Conta).filter_by(id=resultado["conta_id"]).one()
    assert conta.tenant_id == TENANT_A
    assert conta.origem == "rede_social_signal"
    assert conta.porte == "grande"

    sinal_atualizado = sinal_oportunidade_service.listar(db_session, TENANT_A)[0]
    assert sinal_atualizado["status"] == "convertido"
    assert sinal_atualizado["conta_id_gerada"] == conta.id


def test_converter_sinal_ja_convertido_levanta_erro(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)
    sinal_oportunidade_service.converter_em_oportunidade(db_session, TENANT_A, None, sinais[0]["id"])

    try:
        sinal_oportunidade_service.converter_em_oportunidade(db_session, TENANT_A, None, sinais[0]["id"])
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_operar_sinal_inexistente_levanta_erro(db_session):
    try:
        sinal_oportunidade_service.marcar_visto(db_session, TENANT_A, 9999)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_isolamento_por_tenant(db_session):
    _criar_icp(db_session, TENANT_A)
    _criar_perfil(db_session, TENANT_B, cnae_principal="8610-1/01", sede_uf="SP", porte="grande")
    sinais = sinal_oportunidade_service.gerar_sinais(db_session, TENANT_A)

    assert sinal_oportunidade_service.listar(db_session, TENANT_C) == []
    try:
        sinal_oportunidade_service.marcar_visto(db_session, TENANT_C, sinais[0]["id"])
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
