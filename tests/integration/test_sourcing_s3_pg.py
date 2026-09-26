"""Sourcing S3 em Postgres real (FKs ativas, SAVEPOINT dentro do flush,
trigger de lado). Roda quando `B2BON_TESTE_PG_URL` aponta para um banco
Postgres já migrado (`alembic upgrade head`)."""

import logging
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.contexts.bids.contract  # noqa: F401 — espelho do vendedor
import app.contexts.procurement.contract  # noqa: F401 — espelho do comprador
from app.contexts.bids import contract as bids
from app.contexts.procurement.repositorio import COMPRA
from app.contexts.sourcing import contract as sourcing
from app.core.config import settings
from app.models.contrato_compra import ContratoCompra
from app.models.documento_compras import DocumentoCompras
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.evento_processo import EventoProcesso
from app.models.fornecedor_compras import FornecedorCompras
from app.models.licitacao import Licitacao
from app.models.orgao_publico import OrgaoPublico
from app.models.processo_contratacao import ProcessoContratacao
from app.models.requisito_licitacao import RequisitoLicitacao

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


@pytest.fixture()
def pg():
    engine = create_engine(URL)
    Sessao = sessionmaker(bind=engine)
    tenant = f"pg-s3-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})
    yield Sessao, tenant
    engine.dispose()


def _dados(db, tenant):
    lic = Licitacao(tenant_id=tenant, titulo="Edital PG", modalidade="PUBLIC_TENDER", fonte="MANUAL", status="IDENTIFICADA",
                    valor_estimado=1000.456)
    orgao = OrgaoPublico(tenant_id=tenant, nome="Prefeitura PG")
    fornecedor = FornecedorCompras(tenant_id=tenant, razao_social="Fornecedor PG")
    db.add_all([lic, orgao, fornecedor])
    db.flush()
    proc = ProcessoContratacao(tenant_id=tenant, orgao_id=orgao.id, objeto="Compra PG", status="PLANEJAMENTO")
    db.add(proc)
    db.flush()
    doc_venda = DocumentoLicitacao(tenant_id=tenant, licitacao_id=lic.id, tipo="EDITAL", nome_arquivo="e.pdf", tipo_mime="application/pdf",
                                   tamanho_bytes=1, sha256=uuid.uuid4().hex, conteudo=b"x", paginas_texto=["x"], paginas=1,
                                   fonte="UPLOAD", status_analise="PENDENTE")
    db.add(doc_venda)
    db.flush()
    db.add(RequisitoLicitacao(tenant_id=tenant, licitacao_id=lic.id, documento_id=doc_venda.id, categoria="HABILITACAO",
                              descricao="Certidão", origem="manual", status="confirmado"))
    contrato = ContratoCompra(tenant_id=tenant, orgao_id=orgao.id, processo_id=proc.id, fornecedor_id=fornecedor.id,
                              objeto="Contrato PG", status="VIGENTE")
    db.add(contrato)
    db.flush()
    db.add_all([
        DocumentoCompras(tenant_id=tenant, processo_id=proc.id, contrato_id=contrato.id, tipo="ETP", nome_arquivo="etp.txt",
                         tipo_mime="text/plain", tamanho_bytes=1, sha256=uuid.uuid4().hex, conteudo=b"y", paginas_texto=["y"],
                         paginas=1, fonte="UPLOAD", classificacao="CONFIDENTIAL",
                         achados=[{"categoria": "PRAZO", "descricao": "30 dias", "evidencia": "30 dias", "pagina": 1}],
                         status_analise="ANALISADO"),
        EventoProcesso(tenant_id=tenant, processo_id=proc.id, tipo="TAREFA", descricao="Revisar TR", status="ABERTO"),
    ])
    db.commit()
    return lic, proc


def test_espelho_e_leitura_dupla_no_postgres(pg, monkeypatch):
    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "ESTRITA")
    Sessao, tenant = pg
    with Sessao() as db:
        lic, proc = _dados(db, tenant)
        contagens = {t: db.execute(text(f"SELECT lado, count(*) FROM {t} WHERE tenant_id = :t GROUP BY lado"), {"t": tenant}).all()
                     for t in ("processo_sourcing", "documento_sourcing", "requisito_sourcing", "evento_sourcing", "contrato_sourcing")}
        assert sorted(contagens["processo_sourcing"]) == [("BUY", 1), ("SELL", 1)]
        assert sorted(contagens["requisito_sourcing"]) == [("BUY", 1), ("SELL", 1)]
        assert contagens["evento_sourcing"] == [("BUY", 1)] and contagens["contrato_sourcing"] == [("BUY", 1)]
        bids.repositorio.VENDA.requisitos(db, tenant, lic.id)
        bids.repositorio.VENDA.documentos(db, tenant, lic.id)
        COMPRA.documentos(db, tenant, proc.id)
        assert COMPRA.tipos_de_documento(db, tenant) == {proc.id: {"ETP"}}

        lic.status = "GO"
        db.commit()
        assert bids.repositorio.VENDA.obter_processo(db, tenant, lic.id).status == "GO"  # update espelhado e conferido
        with pytest.raises(Exception, match="nao pode mudar"):
            db.execute(text("UPDATE processo_sourcing SET lado = 'BUY' WHERE tenant_id = :t AND lado = 'SELL'"), {"t": tenant})
        db.rollback()
        relatorio = sourcing.espelho.sincronizar_todos(db, tenant)
        assert relatorio["SELL"]["licitacao"]["espelhados"] == 1  # idempotente sobre dados já espelhados


def test_falha_de_espelho_no_postgres_nao_derruba_a_escrita(pg, monkeypatch, caplog):
    monkeypatch.setattr(settings, "sourcing_leitura_dupla", "COMPARAR")
    Sessao, tenant = pg
    original = sourcing.espelho.gravar

    def quebra_no_meio(conexao, *args, **kwargs):
        conexao.execute(text("SELECT 1/0"))  # erro de banco dentro do SAVEPOINT
        return original(conexao, *args, **kwargs)

    monkeypatch.setattr(sourcing.espelho, "gravar", quebra_no_meio)
    with Sessao() as db, caplog.at_level(logging.ERROR, logger="b2bon.sourcing"):
        db.add(Licitacao(tenant_id=tenant, titulo="Continua", modalidade="RFP", fonte="MANUAL", status="IDENTIFICADA"))
        db.commit()  # a transação do usuário sobrevive ao erro do espelho
        assert db.query(Licitacao).filter_by(tenant_id=tenant, titulo="Continua").count() == 1
    assert "SOURCING_ESPELHO_FALHOU" in caplog.text
