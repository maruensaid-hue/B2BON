"""Teste crítico §64 em Postgres real: saldo 100, duas operações de 75
disparadas ao mesmo tempo em conexões separadas. O `SELECT … FOR UPDATE`
da carteira serializa as reservas: exatamente uma passa.

Roda quando `B2BON_TESTE_PG_URL` aponta para um banco Postgres já migrado
(`alembic upgrade head`); o SQLite da suíte não tem trava de linha.
"""

import os
import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.contexts.finops import carteira, execucoes
from app.contexts.finops.comercial import TipoLote
from app.core.config import settings
from app.services.errors import CreditosInsuficientes

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def test_critico_duas_reservas_simultaneas_so_uma_passa(monkeypatch):
    monkeypatch.setattr(settings, "ai_creditos_modo", "ENFORCE")
    engine = create_engine(URL, pool_size=4)
    Sessao = sessionmaker(bind=engine)
    tenant = f"pg-conc-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})
    with Sessao() as db:
        carteira.conceder(db, tenant, TipoLote.TOPUP, 100, "teste", receita_por_credito=Decimal("0.02"))
        db.commit()

    barreira = threading.Barrier(2)
    resultados: list[str] = []

    def reservar() -> None:
        with Sessao() as db:
            barreira.wait()
            try:
                execucoes.abrir(db, tenant, "tender_terms_of_reference")  # 75
                resultados.append("ok")
            except CreditosInsuficientes:
                resultados.append("sem_saldo")
            except Exception as erro:  # noqa: BLE001 — qualquer outra falha aparece no assert
                resultados.append(f"erro:{type(erro).__name__}:{erro}")

    threads = [threading.Thread(target=reservar) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(resultados) == ["ok", "sem_saldo"]
    with Sessao() as db:
        assert float(carteira.disponivel(db, tenant)) == 25
        assert carteira.reconciliar(db, tenant)["consistente"]
    engine.dispose()


def test_primeiro_uso_simultaneo_nao_quebra_na_criacao_da_carteira(monkeypatch):
    """Tenant novo, sem carteira nem configuração: dois pedidos ao mesmo
    tempo não quebram na unicidade; os dois recebem a resposta de negócio."""
    monkeypatch.setattr(settings, "ai_creditos_modo", "ENFORCE")
    engine = create_engine(URL, pool_size=4)
    Sessao = sessionmaker(bind=engine)
    tenant = f"pg-novo-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})

    barreira = threading.Barrier(2)
    resultados: list[str] = []

    def primeiro_uso() -> None:
        with Sessao() as db:
            barreira.wait()
            try:
                execucoes.abrir(db, tenant, "short_summary")
                resultados.append("ok")
            except CreditosInsuficientes:
                resultados.append("sem_saldo")
            except Exception as erro:  # noqa: BLE001
                resultados.append(f"erro:{type(erro).__name__}")

    threads = [threading.Thread(target=primeiro_uso) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert resultados == ["sem_saldo", "sem_saldo"]  # sem licença: sem franquia, sem saldo
    # a transação recusada é desfeita: nenhuma linha órfã fica para trás
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM carteira_creditos WHERE tenant_id = :t"), {"t": tenant}).scalar() <= 1
    engine.dispose()
