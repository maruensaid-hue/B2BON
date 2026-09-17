from app.models.tenant import Tenant
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento
from app.services import rede_social_service, verificacao_empresa_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

TENANT_ID = "tenant-verificacao"


def _criar_tenant(db_session, **overrides) -> Tenant:
    dados = {"id": TENANT_ID, "razao_social": "Acme Consultoria LTDA"}
    dados.update(overrides)
    tenant = Tenant(**dados)
    db_session.add(tenant)
    db_session.commit()
    return tenant


def test_solicitar_calcula_sinal_de_dominio_correspondente(db_session):
    _criar_tenant(db_session)
    rede_social_service.atualizar_perfil(db_session, TENANT_ID, None, site="https://www.acme.com.br")

    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, "usuario-1", "ana@acme.com.br")

    assert verificacao.dominio_confere is True
    assert verificacao.status == "pendente"
    perfil = rede_social_service.obter_perfil(db_session, TENANT_ID)
    assert perfil.status_verificacao == "pendente"


def test_solicitar_dominio_diferente_nao_confere(db_session):
    _criar_tenant(db_session)
    rede_social_service.atualizar_perfil(db_session, TENANT_ID, None, site="https://acme.com.br")

    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@outraempresa.com")

    assert verificacao.dominio_confere is False


def test_solicitar_encontra_cnpj_no_recorte_da_receita(db_session):
    _criar_tenant(db_session, cnpj="12.345.678/0001-99")
    db_session.add(
        CnpjEstabelecimento(
            cnpj="12345678000199", razao_social="Acme Consultoria LTDA", cnae_principal="6201500",
            uf="SP", situacao_cadastral="ATIVA",
        )
    )
    db_session.commit()

    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")

    assert verificacao.cnpj_encontrado_receita is True


def test_solicitar_cnpj_fora_do_recorte_nao_encontrado(db_session):
    _criar_tenant(db_session, cnpj="12.345.678/0001-99")

    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")

    assert verificacao.cnpj_encontrado_receita is False


def test_solicitar_com_pendente_ja_existente_falha(db_session):
    _criar_tenant(db_session)
    verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")

    try:
        verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "outro@acme.com.br")
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_revisar_aprovar_marca_perfil_como_verificada(db_session):
    _criar_tenant(db_session)
    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")

    revisada = verificacao_empresa_service.revisar(db_session, "super-admin-1", verificacao.id, aprovar=True)

    assert revisada.status == "aprovada"
    perfil = rede_social_service.obter_perfil(db_session, TENANT_ID)
    assert perfil.status_verificacao == "verificada"


def test_revisar_rejeitar_registra_motivo(db_session):
    _criar_tenant(db_session)
    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")

    revisada = verificacao_empresa_service.revisar(
        db_session, "super-admin-1", verificacao.id, aprovar=False, motivo_rejeicao="CNPJ não confere"
    )

    assert revisada.status == "rejeitada"
    assert revisada.motivo_rejeicao == "CNPJ não confere"
    perfil = rede_social_service.obter_perfil(db_session, TENANT_ID)
    assert perfil.status_verificacao == "rejeitada"


def test_revisar_verificacao_ja_decidida_falha(db_session):
    _criar_tenant(db_session)
    verificacao = verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")
    verificacao_empresa_service.revisar(db_session, "super-admin-1", verificacao.id, aprovar=True)

    try:
        verificacao_empresa_service.revisar(db_session, "super-admin-1", verificacao.id, aprovar=False)
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass


def test_revisar_verificacao_inexistente_levanta_erro(db_session):
    try:
        verificacao_empresa_service.revisar(db_session, "super-admin-1", 9999, aprovar=True)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_listar_pendentes_so_traz_pendentes(db_session):
    _criar_tenant(db_session)
    verificacao_empresa_service.solicitar(db_session, TENANT_ID, None, "ana@acme.com.br")
    _criar_tenant(db_session, id="tenant-verificacao-2", razao_social="Beta LTDA")
    aprovada = verificacao_empresa_service.solicitar(db_session, "tenant-verificacao-2", None, "b@beta.com")
    verificacao_empresa_service.revisar(db_session, "super-admin-1", aprovada.id, aprovar=True)

    pendentes = verificacao_empresa_service.listar_pendentes(db_session)

    assert len(pendentes) == 1
    assert pendentes[0].tenant_id == TENANT_ID
