import pytest

from app.models.conta import Conta
from app.models.icp import ICP
from app.services import conta_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-brasilapi"


def _criar_conta(db_session, cnpj: str | None = "11222333000191") -> Conta:
    icp = ICP(
        tenant_id=TENANT_ID,
        grupo_id="grupo-1",
        nome="ICP Teste",
        segmento="Tecnologia",
        porte="PEQUENO",
        regiao="SP",
        cnae_codigos=["6201500"],
        ufs=["SP"],
    )
    db_session.add(icp)
    db_session.flush()

    conta = Conta(tenant_id=TENANT_ID, icp_id=icp.id, cnpj=cnpj, nome="Alpha Tech", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def test_enriquecer_via_brasilapi_mapeia_campos(db_session):
    conta = _criar_conta(db_session)
    resposta_brasilapi = {
        "ddd_telefone_1": "11987654321",
        "email": "contato@alphatech.com.br",
        "descricao_situacao_cadastral": "ATIVA",
        "data_situacao_cadastral": "2010-01-01",
        "descricao_porte": "PEQUENO PORTE",
        "capital_social": 100000.0,
        "cnaes_secundarios": [{"codigo": "6202300", "descricao": "Consultoria em TI"}],
    }

    campos = conta_service.enriquecer_via_brasilapi(
        db_session, TENANT_ID, "1", conta.id, lambda cnpj: resposta_brasilapi
    )

    valores_por_campo = {campo.campo: campo.valor for campo in campos}
    assert valores_por_campo["telefone"] == "11987654321"
    assert valores_por_campo["email"] == "contato@alphatech.com.br"
    assert valores_por_campo["situacao_cadastral"] == "ATIVA"
    assert valores_por_campo["cnaes_secundarios"] == "6202300 - Consultoria em TI"
    assert all(campo.fonte == "brasilapi_cnpj" for campo in campos)


def test_enriquecer_via_brasilapi_ignora_campos_ausentes(db_session):
    conta = _criar_conta(db_session)

    campos = conta_service.enriquecer_via_brasilapi(
        db_session, TENANT_ID, "1", conta.id, lambda cnpj: {"email": "contato@alphatech.com.br"}
    )

    assert len(campos) == 1
    assert campos[0].campo == "email"


def test_enriquecer_via_brasilapi_sem_cnpj_falha(db_session):
    conta = _criar_conta(db_session, cnpj=None)

    with pytest.raises(RegraNegocioViolada):
        conta_service.enriquecer_via_brasilapi(db_session, TENANT_ID, "1", conta.id, lambda cnpj: {})


def test_enriquecer_via_brasilapi_erro_http_vira_regra_negocio_violada(db_session):
    import httpx

    conta = _criar_conta(db_session)

    def cliente_com_erro(cnpj: str) -> dict:
        raise httpx.HTTPError("timeout")

    with pytest.raises(RegraNegocioViolada):
        conta_service.enriquecer_via_brasilapi(db_session, TENANT_ID, "1", conta.id, cliente_com_erro)
