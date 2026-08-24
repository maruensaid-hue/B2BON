import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta
from app.providers.account_data.base import AccountDataProvider
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.web_search.base import WebSearchProvider
from app.services import conta_service

logger = logging.getLogger(__name__)

# Teto por disparo de cron — uma planilha com centenas de linhas processa
# em vários disparos sucessivos (a cada 15 min), não tudo de uma vez;
# evita um único disparo ficar preso demorado demais.
_LIMITE_POR_EXECUCAO = 20


def enfileirar(db: Session, tenant_id: str, conta_ids: list[int]) -> None:
    """Best-effort: chamado depois de já ter comitado as contas — nunca
    trava a criação delas se o enfileiramento falhar por algum motivo."""
    for conta_id in conta_ids:
        db.add(FilaEnriquecimentoConta(tenant_id=tenant_id, conta_id=conta_id))
    db.commit()


def processar_pendentes(
    db: Session,
    llm: LLMProvider,
    site_fetcher: SiteFetcher,
    web_search: WebSearchProvider,
    account_data: AccountDataProvider,
    contact_enrichment: ContactEnrichmentProvider,
    graph: Neo4jClient,
) -> dict:
    """Processa um lote pequeno da fila por vez (cron, `/cron/processar-
    fila-enriquecimento`) — site + decisores por conta, tolerante a falha
    por item (uma empresa sem site descobrível não pode travar as
    outras)."""
    itens = (
        db.query(FilaEnriquecimentoConta)
        .filter_by(status="pendente")
        .order_by(FilaEnriquecimentoConta.id)
        .limit(_LIMITE_POR_EXECUCAO)
        .all()
    )

    concluidos = 0
    falhas = 0
    for item in itens:
        try:
            conta_service.enriquecer(db, item.tenant_id, None, item.conta_id, llm, site_fetcher, web_search)
            conta_service.mapear_decisores(
                db, item.tenant_id, None, item.conta_id, account_data, contact_enrichment, graph
            )
            item.status = "concluido"
            concluidos += 1
        except Exception as erro:
            logger.warning("Falha ao enriquecer conta %s da fila em lote", item.conta_id, exc_info=True)
            item.status = "falhou"
            item.erro = str(erro)[:500]
            falhas += 1
        item.processado_em = datetime.now(UTC)

    db.commit()
    return {"processados": len(itens), "concluidos": concluidos, "falhas": falhas}
