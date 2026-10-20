"""Exclusão de conta e de tenant remove TODOS os dados do enriquecimento de site (conteúdo, coletas, indicadores), sem violar chaves estrangeiras.

O SQLite dos testes comuns não impõe FK por padrão; aqui ele é ligado (`PRAGMA foreign_keys=ON`) para reproduzir o comportamento do PostgreSQL de produção."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.coleta_site import ColetaSiteConta, IndicadorFinanceiroConta
from app.models.conta import Conta
from app.models.conteudo_pagina_site import ConteudoPaginaSite
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import conta_service, tenant_service

TENANT = "tenant-excl-site"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_ligada(conexao, _):
        conexao.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine, autoflush=False)()
    sessao.add(Tenant(id=TENANT, razao_social="Excl Site"))
    sessao.commit()
    yield sessao
    sessao.close()
    engine.dispose()


def _conta_com_dados_de_site(db, nome="Alpha", sem_atividade=True) -> Conta:
    conta = Conta(tenant_id=TENANT, nome=nome, dominio=f"{nome.lower()}.com.br", status="prospectada")
    db.add(conta)
    db.flush()
    original = ColetaSiteConta(tenant_id=TENANT, conta_id=conta.id, dominio=conta.dominio, estado="falhou", fontes=[], avisos=[],
                               dominio_evidencias=[], dominio_limitacoes=[])
    db.add(original)
    db.flush()
    reprocesso = ColetaSiteConta(tenant_id=TENANT, conta_id=conta.id, dominio=conta.dominio, estado="concluida", disparo="reprocesso",
                                 reprocesso_de_id=original.id, fontes=[], avisos=[], dominio_evidencias=[], dominio_limitacoes=[])
    db.add(reprocesso)
    db.flush()
    db.add(IndicadorFinanceiroConta(tenant_id=TENANT, conta_id=conta.id, coleta_id=reprocesso.id, nome="receita_liquida", tipo="publicado",
                                    valor=1.0, moeda="BRL", escala="unidade", valor_original="R$ 1", url_fonte="https://x", trecho="t",
                                    metodo_extracao="m", confianca="alta", origens=[]))
    db.add(ConteudoPaginaSite(tenant_id=TENANT, conta_id=conta.id, url="https://x", conteudo="texto"))
    db.commit()
    return conta


def _restos(db, conta_ids=None) -> dict[str, int]:
    return {m.__tablename__: db.query(m).count() for m in (ColetaSiteConta, IndicadorFinanceiroConta, ConteudoPaginaSite)}


def test_excluir_conta_apaga_coletas_reprocessos_indicadores_e_conteudo(db):
    conta = _conta_com_dados_de_site(db)
    outra = _conta_com_dados_de_site(db, "Beta")

    conta_service.excluir(db, TENANT, None, conta.id)

    assert db.get(Conta, conta.id) is None
    assert db.query(ColetaSiteConta).filter_by(conta_id=conta.id).count() == 0
    assert db.query(IndicadorFinanceiroConta).filter_by(conta_id=conta.id).count() == 0
    assert db.query(ConteudoPaginaSite).filter_by(conta_id=conta.id).count() == 0
    # a outra conta não é tocada
    assert db.query(ColetaSiteConta).filter_by(conta_id=outra.id).count() == 2
    assert db.query(IndicadorFinanceiroConta).filter_by(conta_id=outra.id).count() == 1


def test_excluir_em_lote_apaga_os_dados_do_site_das_contas_elegiveis(db):
    contas = [_conta_com_dados_de_site(db, f"Lote{i}") for i in range(3)]

    resultado = conta_service._excluir_contas_em_lote(db, TENANT, None, contas)

    assert resultado["apagadas"] == 3
    assert _restos(db) == {"coleta_site_conta": 0, "indicador_financeiro_conta": 0, "conteudo_pagina_site": 0}


def test_excluir_tenant_apaga_conteudo_coletas_e_indicadores(db):
    _conta_com_dados_de_site(db)
    db.add(Usuario(tenant_id=TENANT, nome="x", email="x@excl.com", senha_hash="h", papel="admin"))
    db.commit()

    tenant_service.apagar_dados(db, TENANT)

    assert _restos(db) == {"coleta_site_conta": 0, "indicador_financeiro_conta": 0, "conteudo_pagina_site": 0}
    assert db.query(Conta).filter_by(tenant_id=TENANT).count() == 0
