"""Retenção dos históricos que crescem sem parar: sem poda, o banco (Neon, com cota) só aumenta e dados são mantidos além da necessidade.

Roda no cron diário (`POST /cron/podar-historicos`) e é idempotente. Regras (todas protegem o que o produto ainda usa):

* cache de respostas de IA: apaga as entradas VENCIDAS (guardam o texto completo da resposta; o cache só serve antes de `expira_em`);
* execuções da coleta de fonte pública: apaga as finalizadas há mais de `RETENCAO_EXECUCAO_COLETA_DIAS` (90), **nunca** a última `concluida`
  de cada tenant+fonte (é ela que guarda o cursor da coleta incremental) nem execução em andamento;
* coletas de site: apaga as finalizadas há mais de `RETENCAO_COLETA_SITE_DIAS` (180) com os indicadores delas, **exceto**, por conta, a mais
  recente, a última bem-sucedida e a última com domínio confirmado manualmente (a confirmação vale para as coletas seguintes). Coletas que
  sobrevivem e apontavam para uma apagada (reprocesso) passam a ter `reprocesso_de_id` nulo.

* outbox de eventos de domínio já processados (`processado_em` preenchido) há mais de `RETENCAO_EVENTOS_PROCESSADOS_DIAS` (60): só o processador os lê,
  uma vez; evento pendente ou com falha (`processado_em` nulo) nunca é apagado;
* corpus público de licitações: edital sem NENHUMA cópia privada (`licitacao.corpus_id`) e não coletado há mais de `RETENCAO_CORPUS_SEM_VINCULO_DIAS` (365),
  com o histórico dele; edital que algum tenant acompanha nunca sai;
* entregas de webhook `entregue`/`desistida` há mais de `RETENCAO_ENTREGAS_WEBHOOK_DIAS` (90); `pendente` nunca é apagada.

Fora da poda por idade, de propósito: `execucao_sync` (a última com sucesso é o cursor da sincronização), `envio_crm` (o último enviado evita reenvio de
sinais), `audit_log` e o ledger de IA (registro de conformidade/financeiro).

O conteúdo atual das páginas (`conteudo_pagina_site`) não entra aqui: já é limitado a 8 linhas por conta e substituído a cada coleta."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coleta_fonte import ExecucaoColetaFonte
from app.models.coleta_site import ColetaSiteConta, IndicadorFinanceiroConta
from app.models.creditos_ia import CacheRespostaIa
from app.models.entrega_webhook import EntregaWebhook
from app.models.evento_dominio import EventoDominio
from app.models.licitacao import Licitacao
from app.models.licitacao_publica import EventoLicitacaoPublica, LicitacaoPublica

logger = logging.getLogger(__name__)


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _podar_cache_ia(db: Session, agora: datetime) -> int:
    apagados = db.query(CacheRespostaIa).filter(CacheRespostaIa.expira_em <= agora).delete(synchronize_session=False)
    db.commit()
    return apagados


def _podar_execucoes(db: Session, agora: datetime) -> int:
    corte = agora - timedelta(days=settings.retencao_execucao_coleta_dias)
    protegidas = {
        i for (i,) in db.query(func.max(ExecucaoColetaFonte.id))
        .filter(ExecucaoColetaFonte.estado == "concluida").group_by(ExecucaoColetaFonte.tenant_id, ExecucaoColetaFonte.fonte).all()
    }
    candidatas = [
        i for (i,) in db.query(ExecucaoColetaFonte.id)
        .filter(ExecucaoColetaFonte.estado != "em_andamento", ExecucaoColetaFonte.iniciada_em < corte).all()
        if i not in protegidas
    ]
    if candidatas:
        db.query(ExecucaoColetaFonte).filter(ExecucaoColetaFonte.id.in_(candidatas)).delete(synchronize_session=False)
    db.commit()
    return len(candidatas)


def _podar_coletas_site(db: Session, agora: datetime) -> dict:
    corte = agora - timedelta(days=settings.retencao_coleta_site_dias)
    protegidas: set[int] = set()
    # a mais recente de cada conta
    protegidas |= {i for (i,) in db.query(func.max(ColetaSiteConta.id)).group_by(ColetaSiteConta.conta_id).all()}
    # a última bem-sucedida de cada conta
    protegidas |= {
        i for (i,) in db.query(func.max(ColetaSiteConta.id))
        .filter(ColetaSiteConta.estado.in_(("concluida", "concluida_sem_ia"))).group_by(ColetaSiteConta.conta_id).all()
    }
    # a última com confirmação manual de cada conta e domínio (vale para as coletas seguintes)
    protegidas |= {
        i for (i,) in db.query(func.max(ColetaSiteConta.id))
        .filter(ColetaSiteConta.dominio_situacao == "confirmado_manualmente").group_by(ColetaSiteConta.conta_id, ColetaSiteConta.dominio).all()
    }
    candidatas = [
        i for (i,) in db.query(ColetaSiteConta.id)
        .filter(ColetaSiteConta.estado != "em_andamento", ColetaSiteConta.iniciada_em < corte).all()
        if i not in protegidas
    ]
    indicadores = 0
    if candidatas:
        db.query(ColetaSiteConta).filter(ColetaSiteConta.reprocesso_de_id.in_(candidatas), ColetaSiteConta.id.notin_(candidatas)).update(
            {ColetaSiteConta.reprocesso_de_id: None}, synchronize_session=False
        )
        indicadores = db.query(IndicadorFinanceiroConta).filter(IndicadorFinanceiroConta.coleta_id.in_(candidatas)).delete(synchronize_session=False)
        db.query(ColetaSiteConta).filter(ColetaSiteConta.id.in_(candidatas)).delete(synchronize_session=False)
    db.commit()
    return {"coletas": len(candidatas), "indicadores": indicadores}


def _podar_eventos_processados(db: Session, agora: datetime) -> int:
    corte = agora - timedelta(days=settings.retencao_eventos_processados_dias)
    apagados = (
        db.query(EventoDominio)
        .filter(EventoDominio.processado_em.isnot(None), EventoDominio.processado_em < corte)
        .delete(synchronize_session=False)
    )
    db.commit()
    return apagados


def _podar_entregas_webhook(db: Session, agora: datetime) -> int:
    corte = agora - timedelta(days=settings.retencao_entregas_webhook_dias)
    apagadas = (
        db.query(EntregaWebhook)
        .filter(EntregaWebhook.status.in_(("entregue", "desistida")), EntregaWebhook.criado_em < corte)
        .delete(synchronize_session=False)
    )
    db.commit()
    return apagadas


def _podar_corpus_sem_vinculo(db: Session, agora: datetime) -> int:
    corte = agora - timedelta(days=settings.retencao_corpus_sem_vinculo_dias)
    referenciados = db.query(Licitacao.corpus_id).filter(Licitacao.corpus_id.isnot(None))
    ids = [i for (i,) in db.query(LicitacaoPublica.id).filter(LicitacaoPublica.ultima_coleta_em < corte, LicitacaoPublica.id.notin_(referenciados)).all()]
    if ids:
        db.query(EventoLicitacaoPublica).filter(EventoLicitacaoPublica.licitacao_publica_id.in_(ids)).delete(synchronize_session=False)
        db.query(LicitacaoPublica).filter(LicitacaoPublica.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return len(ids)


def podar(db: Session, agora: datetime | None = None) -> dict:
    agora = agora or _agora()
    resultado = {
        "cache_ia_expirado": _podar_cache_ia(db, agora),
        "execucoes_coleta_fonte": _podar_execucoes(db, agora),
        "coletas_de_site": _podar_coletas_site(db, agora),
        "eventos_processados": _podar_eventos_processados(db, agora),
        "entregas_webhook": _podar_entregas_webhook(db, agora),
        "corpus_licitacoes_sem_vinculo": _podar_corpus_sem_vinculo(db, agora),
    }
    logger.info("RETENCAO_PODA %s", resultado)
    return resultado
