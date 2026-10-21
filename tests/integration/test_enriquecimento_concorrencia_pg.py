"""Concorrência real da reserva de créditos de enriquecimento em Postgres: franquia de 4 créditos, duas pesquisas de 4 confirmadas ao mesmo tempo em
conexões separadas — exatamente uma reserva passa; e duas confirmações idênticas (mesma chave) reservam uma única vez. Duas pesquisas de tenants
diferentes contra um orçamento global que só comporta uma: exatamente uma passa.

Roda quando `B2BON_TESTE_PG_URL` aponta para um Postgres já migrado (`alembic upgrade head`); o SQLite da suíte não tem trava de linha, então estes
cenários só são exercidos aqui (CI/staging)."""

import os
import threading
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.contexts.enriquecimento import config, custo, ledger, pesquisa
from app.contexts.enriquecimento.pesquisa import Solicitante
from app.models.conta import Conta
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.services.errors import PesquisaBloqueada

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


class _Provedor(ContactEnrichmentProvider):
    pago = True

    def __init__(self) -> None:
        # Nome exclusivo por teste: o Postgres do CI persiste entre os testes, e reservas/orçamento de um provedor não podem vazar para outro cenário.
        self.nome_provedor = f"lusha-teste-pg-{uuid.uuid4().hex[:8]}"

    def buscar_contatos(self, filtro):  # nunca usado: o teste só reserva
        raise AssertionError("não deve chamar o provedor")


def _preparar(Sessao, provedor, *, franquia: int, orcamento: int | None = None, tenants: int = 1):
    sufixo = uuid.uuid4().hex[:8]
    ids = [f"pg-enriq-{sufixo}-{i}" for i in range(tenants)]
    with Sessao() as db:
        plano = Plano(nome=f"Plano PG {sufixo}", franquia_contas_mes=10, max_usuarios=5, preco_mensal=0.0, modulos_contratados=["predator"])
        db.add(plano)
        for tenant in ids:
            db.add(Tenant(id=tenant, razao_social=tenant))
        db.flush()
        for tenant in ids:
            db.add(Licenca(tenant_id=tenant, plano_id=plano.id, status="ativa"))
        db.commit()
        config.definir_config(db, plano_id=plano.id, tenant_id=None, ator_id="1", tenant_auditoria=ids[0], motivo="teste pg", aprovar=True, campos=dict(
            franquia_creditos=franquia, periodicidade="mensal", decisores_por_empresa_padrao=2, decisores_por_empresa_max=2, itens_por_lote_max=5,
            limite_creditos_pesquisa=100_000))
        lote = config.registrar_lote_compra(db, provedor=provedor.nome_provedor, referencia=f"LOTE-{sufixo}", quantidade_creditos=400,
                                            custo_total_brl=Decimal("269.94"), comprado_em=datetime(2026, 10, 21), ator_id="1", tenant_auditoria=ids[0])
        config.definir_politica(
            db, provedor=provedor.nome_provedor, creditos_busca_por_resultado=0, creditos_email=1, creditos_telefone=None, revelar_emails=True,
            revelar_telefones=False, tamanho_pagina_busca=10, creditos_cliente_por_credito_provedor=1, markup_percentual=Decimal("100"),
            metodo_custo="lote_referencia", lote_compra_id=lote.id, casas_exibicao=2, fonte_tarifas="manual", ator_id="1", tenant_auditoria=ids[0],
            motivo="teste pg", aprovar=True)
        custo.definir_custo(db, provedor=provedor.nome_provedor, custo_mensal_usd="600", creditos_anuais=81600, cambio_planejamento_brl="6.00",
                                       ator_id="1", tenant_auditoria=ids[0], motivo="teste pg", aprovar=True)
        if orcamento is not None:
            config.definir_orcamento_global(db, provedor=provedor.nome_provedor, limite_creditos=orcamento, alerta_percentual=80, ator_id="1",
                                            tenant_auditoria=ids[0], motivo="teste pg", aprovar=True)
    return ids


def _previa(Sessao, tenant: str, provedor):
    with Sessao() as db:
        contas = [Conta(tenant_id=tenant, nome=f"Empresa {tenant} {i}", dominio=f"{tenant}-{i}.com.br", cnpj=f"{uuid.uuid4().int % 10**14:014d}",
                        status="prospectada") for i in range(2)]
        db.add_all(contas)
        db.commit()
        return pesquisa.estimar(db, solicitante=Solicitante(id=1, papel="admin", tenant_id=tenant), conta_ids=[c.id for c in contas],
                                decisores_por_empresa=None, provider=provedor).id


def _confirmar_em_paralelo(Sessao, itens, provedor):
    """itens: lista de (tenant, pesquisa_id, chave). Dispara todos ao mesmo tempo; devolve o resultado de cada um ('ok' ou o código do bloqueio)."""
    barreira = threading.Barrier(len(itens))
    resultados: list[str] = []

    def confirmar(tenant: str, pesquisa_id: str, chave: str) -> None:
        with Sessao() as db:
            hash_ = pesquisa.obter(db, tenant, Solicitante(id=1, papel="admin", tenant_id=tenant), pesquisa_id).selecao_hash
            barreira.wait()
            try:
                pesquisa.confirmar(db, solicitante=Solicitante(id=1, papel="admin", tenant_id=tenant), pesquisa_id=pesquisa_id, selecao_hash=hash_,
                                   idempotency_key=chave, provider=provedor)
                resultados.append("ok")
            except PesquisaBloqueada as erro:
                resultados.append(erro.codigo)
            except Exception as erro:  # noqa: BLE001 — qualquer outra falha aparece no assert
                resultados.append(f"erro:{type(erro).__name__}:{erro}")

    threads = [threading.Thread(target=confirmar, args=item) for item in itens]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return resultados


def test_duas_confirmacoes_simultaneas_so_uma_reserva_passa_no_saldo_do_tenant():
    engine = create_engine(URL, pool_size=6)
    Sessao = sessionmaker(bind=engine)
    provedor = _Provedor()
    (tenant,) = _preparar(Sessao, provedor, franquia=4, orcamento=1000)
    p1, p2 = _previa(Sessao, tenant, provedor), _previa(Sessao, tenant, provedor)  # cada uma precisa de 4

    resultados = _confirmar_em_paralelo(Sessao, [(tenant, p1, f"chave-{uuid.uuid4().hex}"), (tenant, p2, f"chave-{uuid.uuid4().hex}")], provedor)

    assert sorted(resultados) == ["ok", "saldo_insuficiente"], resultados
    with Sessao() as db:
        assert ledger.reservado(db, tenant) == 4 and ledger.disponivel(db, tenant) == 0
    engine.dispose()


def test_mesma_chave_em_duas_confirmacoes_simultaneas_reserva_uma_unica_vez():
    engine = create_engine(URL, pool_size=6)
    Sessao = sessionmaker(bind=engine)
    provedor = _Provedor()
    (tenant,) = _preparar(Sessao, provedor, franquia=20, orcamento=1000)
    p = _previa(Sessao, tenant, provedor)

    resultados = _confirmar_em_paralelo(Sessao, [(tenant, p, "chave-compartilhada-1"), (tenant, p, "chave-compartilhada-1")], provedor)

    assert all(r == "ok" for r in resultados), resultados  # a segunda recebe o estado da primeira
    with Sessao() as db:
        assert ledger.reservado(db, tenant) == 4
    engine.dispose()


def test_orcamento_global_so_comporta_uma_pesquisa_de_tenants_diferentes():
    engine = create_engine(URL, pool_size=6)
    Sessao = sessionmaker(bind=engine)
    provedor = _Provedor()
    a, b = _preparar(Sessao, provedor, franquia=10, orcamento=5, tenants=2)
    pa, pb = _previa(Sessao, a, provedor), _previa(Sessao, b, provedor)  # 4 cada; global 5

    resultados = _confirmar_em_paralelo(Sessao, [(a, pa, f"chave-{uuid.uuid4().hex}"), (b, pb, f"chave-{uuid.uuid4().hex}")], provedor)

    assert sorted(resultados) == ["ok", "orcamento_global_esgotado"], resultados
    with Sessao() as db:
        assert ledger.situacao_global(db, provedor.nome_provedor)["reservado"] == 4
    engine.dispose()
