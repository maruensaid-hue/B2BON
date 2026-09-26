"""Phase E em Postgres real: fluxo nativo do comprador privado, trigger de lado
nas tabelas novas e inserções nativas concorrentes sem esperar no índice único.
Roda quando `B2BON_TESTE_PG_URL` aponta para um Postgres migrado."""

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, exc, text
from sqlalchemy.orm import sessionmaker

import app.contexts.procurement.contract  # noqa: F401
from app.contexts.procurement import estrategico
from app.contexts.sourcing import contract as sourcing
from app.models.usuario import Usuario

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


@pytest.fixture()
def pg():
    engine = create_engine(URL)
    tenant = f"pg-e-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})
    yield sessionmaker(bind=engine), tenant
    engine.dispose()


def test_fluxo_nativo_e_lado_imutavel_no_postgres(pg):
    Sessao, tenant = pg
    with Sessao() as db:
        admin = Usuario(tenant_id=tenant, nome="Admin", email=f"{tenant}@x.com", papel="admin", ativo=True)
        db.add(admin)
        db.commit()
        rfq = estrategico.criar_processo(db, tenant, admin.id, {"tipo_processo": "RFQ", "titulo": "Cadeiras PG"})
        item = estrategico.adicionar_item(db, tenant, admin.id, rfq.id, {"descricao": "Cadeira", "quantidade": 3})
        participante = estrategico.convidar(db, tenant, admin.id, rfq.id, {"nome": "Delta"})
        for status in ("PUBLICADO", "RECEBENDO_PROPOSTAS"):
            estrategico.mudar_status(db, tenant, admin.id, rfq.id, status)
        proposta = estrategico.registrar_proposta(db, tenant, admin.id, rfq.id, {
            "participante_id": participante.id, "itens": [{"item_id": item.id, "preco_unitario": 100.25}]})
        assert float(proposta.valor_total) == 300.75
        estrategico.solicitar_aprovacao(db, tenant, admin.id, rfq.id, participante.id, "Único")
        estrategico.decidir_aprovacao(db, tenant, admin, rfq.id, True, None)
        contrato = estrategico.contratar(db, tenant, admin.id, rfq.id, {})
        assert (contrato.lado, float(contrato.valor_inicial), rfq.origem_id) == ("BUY", 300.75, rfq.id)
        assert sourcing.nativo.listar(db, "proposta", sourcing.tipos.Lado.VENDA, tenant) == []
        for tabela in ("participante_sourcing", "item_sourcing", "proposta_sourcing", "proposta_item_sourcing"):
            with pytest.raises(exc.DBAPIError):
                db.execute(text(f"UPDATE {tabela} SET lado = 'SELL' WHERE tenant_id = :t"), {"t": tenant})
            db.rollback()


def test_insercoes_nativas_concorrentes_nao_se_bloqueiam(pg):
    """Duas transações abertas criando processo nativo ao mesmo tempo: com o provisório único,
    nenhuma espera a outra no índice único (origem_tabela, origem_id)."""
    Sessao, tenant = pg
    pronto, liberar, erros, ids = threading.Barrier(2), threading.Event(), [], []

    def criar():
        with Sessao() as db:
            try:
                db.execute(text("SET lock_timeout = '2s'"))
                processo = sourcing.nativo.criar(db, "processo", sourcing.tipos.Lado.COMPRA, tenant, segmento="ENTERPRISE",
                                                 tipo_processo="RFP", titulo="Concorrente", status="RASCUNHO",
                                                 classificacao="CONFIDENTIAL", workflow="ENTERPRISE_SOURCING_BUY@1", fonte="MANUAL")
                pronto.wait(timeout=5)  # as duas com a linha inserida e a transação aberta
                liberar.wait(timeout=5)
                db.commit()
                ids.append(processo.id)
            except Exception as erro:  # noqa: BLE001 — o teste reporta
                erros.append(erro)

    threads = [threading.Thread(target=criar) for _ in range(2)]
    for t in threads:
        t.start()
    liberar.set()
    for t in threads:
        t.join(timeout=15)
    assert erros == [] and len(set(ids)) == 2
