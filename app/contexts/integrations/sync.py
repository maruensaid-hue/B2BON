"""Framework de sincronização (Fase 3, §13).

`sincronizar(db, conexao, entidade, destino)`:
- incremental: usa o `iniciado_em` da última execução com sucesso como
  `updated_since` (quando o adapter declara `incremental_sync`);
- paginação por cursor até o fim ou `max_paginas`;
- retry com backoff exponencial por página (`com_retry`), só para erros
  transitórios (`ErroTransitorio`, timeouts de rede);
- registra `ExecucaoSync` (itens, páginas, tentativas, erro) e atualiza
  `ConexaoIntegracao.ultimo_sync_em/ultimo_erro`.

`destino` recebe cada página de entidades canônicas. O que fazer com elas
(upsert no CRM interno, cálculo do MAP, …) é decisão do consumidor
(Fase 13); aqui o default só conta.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.contexts.integrations import registry
from app.models.conexao_integracao import ConexaoIntegracao
from app.models.execucao_sync import ExecucaoSync

logger = logging.getLogger(__name__)

ENTIDADES = {
    "organizations": "list_organizations",
    "accounts": "list_accounts",
    "people": "list_people",
    "opportunities": "list_opportunities",
    "contacts": "list_contacts",
    "customers": "list_customers",
    "activities": "list_activities",
    "cs_metrics": "list_cs_metrics",
}
_COM_UPDATED_SINCE = {"organizations", "accounts", "people", "opportunities"}


class ErroTransitorio(Exception):
    """Falha que vale tentar de novo (429, 5xx, timeout)."""


def com_retry(funcao: Callable, tentativas: int = 3, espera_base: float = 1.0, dormir: Callable[[float], None] = time.sleep):
    ultima: Exception | None = None
    for tentativa in range(tentativas):
        try:
            return funcao(), tentativa + 1
        except (ErroTransitorio, httpx.TransportError) as erro:
            ultima = erro
            if tentativa < tentativas - 1:
                dormir(espera_base * (2**tentativa))
    raise ultima  # type: ignore[misc]


def sincronizar(
    db: Session,
    conexao: ConexaoIntegracao,
    entidade: str,
    destino: Callable[[list], None] | None = None,
    max_paginas: int = 50,
    dormir: Callable[[float], None] = time.sleep,
) -> ExecucaoSync:
    if entidade not in ENTIDADES:
        raise ValueError(f"Entidade de sync desconhecida: {entidade}")
    adapter = registry.obter_adapter(db, conexao)
    ultima_ok = (
        db.query(ExecucaoSync)
        .filter_by(conexao_id=conexao.id, entidade=entidade, status="sucesso")
        .order_by(ExecucaoSync.id.desc())
        .first()
    )
    incremental = (
        ultima_ok.iniciado_em
        if ultima_ok and adapter.capabilities().incremental_sync and entidade in _COM_UPDATED_SINCE
        else None
    )
    execucao = ExecucaoSync(
        conexao_id=conexao.id, tenant_id=conexao.tenant_id, entidade=entidade, status="executando",
        incremental_desde=incremental, itens_lidos=0, paginas=0, tentativas=0, iniciado_em=datetime.now(UTC),
    )
    db.add(execucao)
    db.commit()

    listar = getattr(adapter, ENTIDADES[entidade])
    kwargs = {"updated_since": incremental} if incremental is not None else {}
    cursor = None
    try:
        while execucao.paginas < max_paginas:
            pagina, tentativas = com_retry(lambda: listar(conexao.tenant_id, cursor=cursor, **kwargs), dormir=dormir)
            execucao.tentativas += tentativas
            execucao.paginas += 1
            execucao.itens_lidos += len(pagina.items)
            if destino is not None:
                destino(pagina.items)
            cursor = pagina.next_cursor
            if not cursor:
                break
        execucao.status = "sucesso"
        conexao.ultimo_sync_em = datetime.now(UTC)
        conexao.ultimo_erro = None
    except Exception as erro:  # noqa: BLE001 — registra e reporta, não derruba o cron
        execucao.status = "falha"
        execucao.erro = f"{type(erro).__name__}: {erro}"[:500]
        conexao.ultimo_erro = execucao.erro
        logger.exception("Falha no sync da conexão %s (%s)", conexao.id, entidade)
    execucao.finalizado_em = datetime.now(UTC)
    db.commit()
    return execucao
