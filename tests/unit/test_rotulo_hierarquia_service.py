import pytest

from app.models.rotulo_tipo_tenant import RotuloTipoTenant
from app.services import rotulo_hierarquia_service
from app.services.errors import ValidacaoFalhou


def test_listar_cria_os_padroes_na_primeira_leitura(db_session):
    rotulos = rotulo_hierarquia_service.listar(db_session)

    assert [r.tipo for r in rotulos] == ["distribuidor", "revendedor", "cliente"]
    assert [r.rotulo for r in rotulos] == ["Master", "Vendedor", "Cliente"]
    assert db_session.query(RotuloTipoTenant).count() == 3


def test_listar_e_idempotente_nao_duplica_linhas(db_session):
    rotulo_hierarquia_service.listar(db_session)
    rotulo_hierarquia_service.listar(db_session)

    assert db_session.query(RotuloTipoTenant).count() == 3


def test_atualizar_troca_os_tres_rotulos(db_session):
    atualizados = rotulo_hierarquia_service.atualizar(db_session, "Franqueadora", "Franqueado", "Consumidor")

    assert {r.tipo: r.rotulo for r in atualizados} == {
        "distribuidor": "Franqueadora",
        "revendedor": "Franqueado",
        "cliente": "Consumidor",
    }
    persistidos = {r.tipo: r.rotulo for r in db_session.query(RotuloTipoTenant).all()}
    assert persistidos == {
        "distribuidor": "Franqueadora",
        "revendedor": "Franqueado",
        "cliente": "Consumidor",
    }


def test_atualizar_com_rotulo_vazio_recusa(db_session):
    with pytest.raises(ValidacaoFalhou):
        rotulo_hierarquia_service.atualizar(db_session, "Master", "  ", "Cliente")
