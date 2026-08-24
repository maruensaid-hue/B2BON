from app.models.conta import Conta
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.providers.web_search.base import ResultadoBusca
from app.services import enriquecimento_fila_service
from tests.fakes import FakeAccountDataProvider, FakeContactEnrichmentProvider, FakeGraphClient, FakeLLMProvider, FakeWebSearchProvider

TENANT_ID = "tenant-fila-enriquecimento"


def _criar_conta(db_session, nome: str = "Alpha Tech", dominio: str | None = None) -> Conta:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome=nome, dominio=dominio, status="prospectada")
    db_session.add(conta)
    db_session.commit()
    return conta


def _site_fetcher(resposta: str = "=== https://alphatech.com.br ===\nConteúdo institucional."):
    return lambda dominio: resposta


def test_enfileirar_cria_itens_pendentes(db_session):
    conta1 = _criar_conta(db_session, "Empresa A")
    conta2 = _criar_conta(db_session, "Empresa B")

    enriquecimento_fila_service.enfileirar(db_session, TENANT_ID, [conta1.id, conta2.id])

    itens = db_session.query(FilaEnriquecimentoConta).order_by(FilaEnriquecimentoConta.id).all()
    assert len(itens) == 2
    assert all(item.status == "pendente" for item in itens)
    assert {item.conta_id for item in itens} == {conta1.id, conta2.id}


def test_processar_pendentes_enriquece_site_e_marca_concluido(db_session):
    conta = _criar_conta(db_session, "Alpha Tech", dominio="alphatech.com.br")
    enriquecimento_fila_service.enfileirar(db_session, TENANT_ID, [conta.id])
    llm = FakeLLMProvider(["porte: media"])

    resultado = enriquecimento_fila_service.processar_pendentes(
        db_session, llm, _site_fetcher(), FakeWebSearchProvider(),
        FakeAccountDataProvider(), FakeContactEnrichmentProvider(), FakeGraphClient(),
    )

    assert resultado == {"processados": 1, "concluidos": 1, "falhas": 0}
    item = db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta.id).one()
    assert item.status == "concluido"
    assert item.processado_em is not None


def test_processar_pendentes_tolera_falha_sem_derrubar_outros_itens(db_session):
    """Conta sem domínio e sem resultado de busca aceitável faz `enriquecer`
    levantar RegraNegocioViolada — não pode travar o resto do lote."""
    conta_falha = _criar_conta(db_session, "Empresa Sem Site", dominio=None)
    conta_ok = _criar_conta(db_session, "Alpha Tech", dominio="alphatech.com.br")
    enriquecimento_fila_service.enfileirar(db_session, TENANT_ID, [conta_falha.id, conta_ok.id])
    llm = FakeLLMProvider(["porte: media"])
    web_search = FakeWebSearchProvider([ResultadoBusca(titulo="no LinkedIn", url="https://www.linkedin.com/company/x", descricao="")])

    resultado = enriquecimento_fila_service.processar_pendentes(
        db_session, llm, _site_fetcher(), web_search,
        FakeAccountDataProvider(), FakeContactEnrichmentProvider(), FakeGraphClient(),
    )

    assert resultado == {"processados": 2, "concluidos": 1, "falhas": 1}
    item_falha = db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta_falha.id).one()
    item_ok = db_session.query(FilaEnriquecimentoConta).filter_by(conta_id=conta_ok.id).one()
    assert item_falha.status == "falhou"
    assert item_falha.erro is not None
    assert item_ok.status == "concluido"


def test_processar_pendentes_respeita_limite_por_execucao(db_session, monkeypatch):
    monkeypatch.setattr(enriquecimento_fila_service, "_LIMITE_POR_EXECUCAO", 1)
    conta1 = _criar_conta(db_session, "Empresa A", dominio="a.com.br")
    conta2 = _criar_conta(db_session, "Empresa B", dominio="b.com.br")
    enriquecimento_fila_service.enfileirar(db_session, TENANT_ID, [conta1.id, conta2.id])
    llm = FakeLLMProvider(["porte: media", "porte: media"])

    resultado = enriquecimento_fila_service.processar_pendentes(
        db_session, llm, _site_fetcher(), FakeWebSearchProvider(),
        FakeAccountDataProvider(), FakeContactEnrichmentProvider(), FakeGraphClient(),
    )

    assert resultado["processados"] == 1
    pendentes_restantes = db_session.query(FilaEnriquecimentoConta).filter_by(status="pendente").count()
    assert pendentes_restantes == 1
