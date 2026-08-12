import pytest

from app.models.conta import Conta
from app.providers.web_search.base import ResultadoBusca
from app.services import conta_service
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider, FakeWebSearchProvider

TENANT_ID = "tenant-enriquecer-site"


def _criar_conta(db_session, dominio: str | None = None) -> Conta:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome="Alpha Tech", dominio=dominio, status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def _site_fetcher(resposta: str = "=== https://alphatech.com.br ===\nConteúdo institucional."):
    return lambda dominio: resposta


def test_enriquecer_sem_dominio_descobre_e_persiste(db_session):
    conta = _criar_conta(db_session, dominio=None)
    web_search = FakeWebSearchProvider([ResultadoBusca(titulo="Alpha Tech", url="https://www.alphatech.com.br/", descricao="")])
    llm = FakeLLMProvider(["porte: media"])

    conta_service.enriquecer(db_session, TENANT_ID, "1", conta.id, llm, _site_fetcher(), web_search)

    db_session.refresh(conta)
    assert conta.dominio == "www.alphatech.com.br"
    assert web_search.buscas == ["Alpha Tech site oficial"]


def test_enriquecer_sem_dominio_e_sem_resultado_aceitavel_falha(db_session):
    conta = _criar_conta(db_session, dominio=None)
    web_search = FakeWebSearchProvider([ResultadoBusca(titulo="Alpha Tech no LinkedIn", url="https://www.linkedin.com/company/alpha-tech", descricao="")])
    llm = FakeLLMProvider(["porte: media"])

    with pytest.raises(RegraNegocioViolada):
        conta_service.enriquecer(db_session, TENANT_ID, "1", conta.id, llm, _site_fetcher(), web_search)


def test_enriquecer_com_dominio_ja_cadastrado_nao_busca_na_web(db_session):
    conta = _criar_conta(db_session, dominio="alphatech.com.br")
    web_search = FakeWebSearchProvider()
    llm = FakeLLMProvider(["porte: media"])

    conta_service.enriquecer(db_session, TENANT_ID, "1", conta.id, llm, _site_fetcher(), web_search)

    assert web_search.buscas == []


def test_descobrir_dominio_ignora_dominio_bloqueado_e_pega_o_proximo(db_session):
    web_search = FakeWebSearchProvider(
        [
            ResultadoBusca(titulo="Alpha Tech no LinkedIn", url="https://www.linkedin.com/company/alpha-tech", descricao=""),
            ResultadoBusca(titulo="Alpha Tech", url="https://alphatech.com.br/sobre", descricao=""),
        ]
    )

    dominio = conta_service._descobrir_dominio("Alpha Tech", web_search)

    assert dominio == "alphatech.com.br"
