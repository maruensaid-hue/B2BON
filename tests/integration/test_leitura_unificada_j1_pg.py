"""Phase J1 em Postgres real: a leitura pelas tabelas unificadas devolve o mesmo que a antiga (ordem com
vazios incluída, que no Postgres ficam por último). Roda quando `B2BON_TESTE_PG_URL` aponta para um Postgres
migrado."""

import os
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.contexts.bids.contract  # noqa: F401 — instala o espelho do lado vendedor
from app.contexts.bids import licitacoes, repositorio
from app.contexts.sourcing import contract as sourcing
from app.core.config import settings
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.requisito_licitacao import RequisitoLicitacao

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def _ler(db, tenant, ids):
    pagina = repositorio.VENDA.listar_processos(db, tenant, limite=50)
    return {
        "processos": [licitacoes.como_dict(p) for p in pagina.itens],
        "requisitos": {i: [licitacoes.requisito_dict(r) for r in repositorio.VENDA.requisitos(db, tenant, i, True)] for i in ids},
        "documentos": {i: [d.id for d in repositorio.VENDA.documentos(db, tenant, i)] for i in ids},
    }


def test_leitura_unificada_igual_a_antiga_no_postgres(monkeypatch):
    engine = create_engine(URL)
    tenant = f"pg-j1-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})
    Sessao = sessionmaker(bind=engine)
    try:
        with Sessao() as db:
            agora = datetime(2026, 10, 1, 12, 0)
            lics = [Licitacao(tenant_id=tenant, titulo=f"L{i}", modalidade="PUBLIC_TENDER", fonte="MANUAL", status="IDENTIFICADA",
                              prazo_proposta=prazo, valor_estimado=1000.5)
                    for i, prazo in enumerate((agora + timedelta(days=5), None, agora + timedelta(days=5), agora))]
            db.add_all(lics)
            db.flush()
            doc = DocumentoLicitacao(tenant_id=tenant, licitacao_id=lics[0].id, tipo="TR", nome_arquivo="tr.txt", tipo_mime="text/plain",
                                     tamanho_bytes=3, sha256="a" * 64, paginas=1, fonte="UPLOAD", status_analise="PENDENTE")
            db.add(doc)
            db.flush()
            for documento_id, pagina in ((None, None), (doc.id, 2), (doc.id, None), (None, 1)):
                db.add(RequisitoLicitacao(tenant_id=tenant, licitacao_id=lics[0].id, documento_id=documento_id, pagina=pagina,
                                          categoria="PRAZO", descricao="Requisito", origem="manual", status="confirmado"))
            db.commit()
            ids = [lic.id for lic in lics]
            sourcing.espelho.sincronizar_todos(db, tenant)
        with Sessao() as db:
            monkeypatch.setattr(settings, "sourcing_leitura_fonte", "ANTIGA")
            antiga = _ler(db, tenant, ids)
            monkeypatch.setattr(settings, "sourcing_leitura_fonte", "UNIFICADA")
            unificada = _ler(db, tenant, ids)
        assert unificada == antiga
        assert [r["documento_id"] for r in antiga["requisitos"][ids[0]]][-2:] == [None, None]  # Postgres: vazios por último
    finally:
        engine.dispose()
