"""Execução da pesquisa de decisores: envio ao provedor, liquidação dos créditos, retomada, cancelamento e reconciliação.

Só roda depois de `pesquisa.confirmar` ter gravado a reserva. Cada empresa é registrada como `enviado` ANTES da chamada ao provedor e liquidada
(consumo + liberação do que sobrou) na mesma transação em que os decisores são gravados. Desfecho ambíguo não é repetido nem liberado.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import ledger
from app.contexts.enriquecimento.config import agora_utc
from app.contexts.enriquecimento.pesquisa import (
    FALHAS_SEGUIDAS_PARA_PARAR,
    Solicitante,
    _mudar_estado,
    _mudar_estado_item,
    _registrar_transicao,
    itens_de,
    obter,
)
from app.core.config import settings
from app.graph.client import Neo4jClient
from app.models.conta import Conta
from app.models.enriquecimento_creditos import PesquisaDecisores, PesquisaDecisoresEmpresa
from app.models.lista_prospeccao import ListaProspeccao
from app.providers.contact_enrichment.base import ContactEnrichmentProvider, FiltroContatos, ResultadoBuscaContatos
from app.services import atividade_service, auditoria_service
from app.services.errors import NaoEncontrado, PesquisaBloqueada, ValidacaoFalhou

logger = logging.getLogger("b2bon.enriquecimento")


def _liquidar_item(db: Session, pesquisa: PesquisaDecisores, item: PesquisaDecisoresEmpresa, consumidos: int, *, origem: str,
                   motivo: str | None, ator_id: str | None, agora: datetime) -> None:
    """Converte a reserva da empresa em consumo (`consumidos`) e libera o restante. Idempotente por item (chaves fixas no razão)."""
    reservados = item.creditos_reservados
    if consumidos < 0 or consumidos > reservados:
        raise ValueError("consumo fora do intervalo reservado")
    ledger.travar_carteira(db, pesquisa.tenant_id)
    if consumidos > 0:
        ledger.lancar(db, pesquisa.tenant_id, "CONSUMO", delta_saldo=-consumidos, delta_reservado=-consumidos, provedor=pesquisa.provedor,
                      pesquisa_id=pesquisa.id, item_id=item.id, origem=origem, motivo=motivo, ator_id=ator_id,
                      idempotency_key=f"consumo:{item.id}", agora=agora)
    if reservados > consumidos:
        ledger.lancar(db, pesquisa.tenant_id, "LIBERACAO", delta_reservado=-(reservados - consumidos), provedor=pesquisa.provedor,
                      pesquisa_id=pesquisa.id, item_id=item.id, origem=origem, motivo=motivo, ator_id=ator_id,
                      idempotency_key=f"liberacao:{item.id}", agora=agora)
    item.creditos_consumidos = consumidos


def _marcar_envios_antigos_como_ambiguos(db: Session, pesquisa: PesquisaDecisores, agora: datetime) -> None:
    """Empresa 'enviada' há tempo demais sem desfecho (o processo morreu no meio): ninguém sabe se o provedor revelou, então é ambígua."""
    corte = agora - timedelta(minutes=settings.enriquecimento_item_enviado_stale_min)
    for item in itens_de(db, pesquisa.id):
        if item.estado == "enviado" and item.enviado_em is not None and item.enviado_em <= corte:
            _mudar_estado_item(db, pesquisa, item, "ambiguo", "enviado_sem_desfecho", None)
            pesquisa.requer_reconciliacao = True


def _finalizar(db: Session, pesquisa: PesquisaDecisores, ator_id: str | None) -> None:
    itens = itens_de(db, pesquisa.id)
    if any(i.estado in ("pendente", "enviado") for i in itens):
        return
    pesquisa.creditos_consumidos = sum(i.creditos_consumidos for i in itens)
    if any(i.estado == "ambiguo" for i in itens):
        pesquisa.requer_reconciliacao = True
        if pesquisa.estado != "em_processamento":
            _mudar_estado(db, pesquisa, "em_processamento", "aguardando_reconciliacao: ha empresa com desfecho ambiguo", ator_id)
        return
    houve_falha = any(i.estado == "falha" for i in itens)
    houve_sucesso = any(i.estado in ("concluido", "sem_resultados", "deduplicada") for i in itens)
    novo = "concluida" if not houve_falha else ("parcial" if houve_sucesso else "falha")
    _mudar_estado(db, pesquisa, novo, f"consumidos={pesquisa.creditos_consumidos} reservados={pesquisa.creditos_reservados}", ator_id)


def _filtro_da_empresa(db: Session, tenant_id: str, conta: Conta, item: PesquisaDecisoresEmpresa) -> FiltroContatos:
    filtro: dict = {"nome_empresa": conta.nome_fantasia or conta.nome, "dominio": conta.dominio, "cnpj": conta.cnpj,
                    "limite_contatos": item.decisores_solicitados}
    if conta.lista_prospeccao_id:
        lista = db.query(ListaProspeccao).filter_by(id=conta.lista_prospeccao_id, tenant_id=tenant_id).one_or_none()
        if lista is not None and lista.cargos_alvo:
            filtro["cargos_alvo"] = lista.cargos_alvo
    return FiltroContatos(**filtro)


def executar(db: Session, *, tenant_id: str, pesquisa_id: str, provider: ContactEnrichmentProvider, graph: Neo4jClient,
             ator_id: str | None, agora: datetime | None = None) -> PesquisaDecisores:
    """Envia ao provedor, empresa por empresa, o que está reservado. Só avança de `reservada`/`enviada`; retomar uma pesquisa interrompida
    processa apenas as empresas ainda `pendente` (nunca repete uma já enviada)."""
    # Import tardio: o contrato do PREDATOR puxa a cadeia de contextos (sourcing → intelligence) e, importado primeiro, quebra por ciclo já
    # existente; aqui o app já está carregado.
    from app.contexts.predator.contract import registrar_candidatos

    agora = agora or agora_utc()
    pesquisa = db.query(PesquisaDecisores).filter_by(id=pesquisa_id, tenant_id=tenant_id).one_or_none()
    if pesquisa is None:
        raise NaoEncontrado("Pesquisa não encontrada.")
    if pesquisa.estado not in ("reservada", "enviada"):
        return pesquisa
    if provider.nome_provedor != pesquisa.provedor or not provider.disponivel:
        raise PesquisaBloqueada("O provedor desta pesquisa não está disponível. Nada foi enviado.", "provedor_indisponivel")
    if pesquisa.estado == "reservada":
        _mudar_estado(db, pesquisa, "enviada", "inicio_do_envio", ator_id)
    _marcar_envios_antigos_como_ambiguos(db, pesquisa, agora)
    db.commit()

    seguidas = 0
    for item in itens_de(db, pesquisa.id):
        if item.estado != "pendente":
            continue
        if seguidas >= FALHAS_SEGUIDAS_PARA_PARAR:
            logger.warning("ENRIQUECIMENTO_PAUSA pesquisa=%s apos=%s falhas seguidas; o restante fica pendente", pesquisa.id, seguidas)
            break
        conta = db.query(Conta).filter_by(id=item.conta_id, tenant_id=tenant_id).one()
        filtro = _filtro_da_empresa(db, tenant_id, conta, item)

        # Reivindicação atômica: só quem trocar `pendente` por `enviado` chama o provedor (duas execuções paralelas nunca enviam a mesma empresa).
        reivindicada = db.query(PesquisaDecisoresEmpresa).filter(
            PesquisaDecisoresEmpresa.id == item.id, PesquisaDecisoresEmpresa.estado == "pendente",
        ).update({"estado": "enviado", "enviado_em": agora_utc(), "tentativas": item.tentativas + 1}, synchronize_session=False)
        if not reivindicada:
            db.rollback()
            continue
        db.refresh(item)
        _registrar_transicao(db, pesquisa, "enviado", "chamada_ao_provedor", ator_id, item=item, anterior="pendente")
        db.commit()  # rastro gravado antes de o provedor ser chamado

        try:
            resultado = provider.buscar_contatos_governado(filtro)
        except Exception:  # noqa: BLE001 — qualquer exceção depois do envio é desfecho desconhecido
            logger.exception("ENRIQUECIMENTO_EXCECAO pesquisa=%s item=%s", pesquisa.id, item.id)
            resultado = ResultadoBuscaContatos(estado="ambiguo", detalhe="excecao_no_adaptador")

        item.ids_provedor = list(resultado.ids_provedor) or None
        agora_item = agora_utc()
        if resultado.estado == "ok":
            revelados = len(resultado.contatos)
            consumidos = min(revelados, item.creditos_reservados)
            novos = registrar_candidatos(db, tenant_id, conta, resultado.contatos[: item.decisores_solicitados], graph)
            item.decisores_retornados = revelados
            motivo = None
            if revelados > item.decisores_solicitados:
                motivo = f"provedor_acima_do_limite:{revelados}/{item.decisores_solicitados}"
                pesquisa.requer_reconciliacao = True
                logger.error("ENRIQUECIMENTO_ACIMA_DO_LIMITE pesquisa=%s item=%s revelados=%s limite=%s", pesquisa.id, item.id, revelados,
                             item.decisores_solicitados)
            _liquidar_item(db, pesquisa, item, consumidos, origem="execucao", motivo=motivo, ator_id=ator_id, agora=agora_item)
            _mudar_estado_item(db, pesquisa, item, "concluido", motivo or f"revelados={revelados}", ator_id)
            atividade_service.registrar(db, tenant_id, conta_id=conta.id, tipo="sistema",
                                        descricao=f"Pesquisa de decisores: {novos} decisor(es) novo(s) via {provider.nome_provedor}", ator_id=ator_id)
            auditoria_service.registrar(db, tenant_id, "decisores_pesquisados", "conta", conta.id, ator_id,
                                        {"pesquisa_id": pesquisa.id, "novos": novos, "creditos": consumidos}, conta_id=conta.id)
            seguidas = 0
        elif resultado.estado == "sem_resultados":
            _liquidar_item(db, pesquisa, item, 0, origem="execucao", motivo="sem_resultados", ator_id=ator_id, agora=agora_item)
            _mudar_estado_item(db, pesquisa, item, "sem_resultados", "provedor_sem_resultados", ator_id)
            seguidas = 0
        elif resultado.estado == "erro_seguro":
            _liquidar_item(db, pesquisa, item, 0, origem="execucao", motivo=resultado.detalhe, ator_id=ator_id, agora=agora_item)
            _mudar_estado_item(db, pesquisa, item, "falha", resultado.detalhe or "erro_seguro", ator_id)
            seguidas += 1
        else:  # ambiguo: a reserva fica retida
            _mudar_estado_item(db, pesquisa, item, "ambiguo", resultado.detalhe or "desfecho_desconhecido", ator_id)
            pesquisa.requer_reconciliacao = True
            seguidas += 1
        db.commit()

    _finalizar(db, pesquisa, ator_id)
    db.commit()
    logger.info("ENRIQUECIMENTO_EXECUCAO pesquisa=%s estado=%s consumidos=%s reconciliar=%s", pesquisa.id, pesquisa.estado,
                pesquisa.creditos_consumidos, pesquisa.requer_reconciliacao)
    return pesquisa


def retomar(db: Session, *, solicitante: Solicitante, pesquisa_id: str, provider: ContactEnrichmentProvider, graph: Neo4jClient) -> PesquisaDecisores:
    """Continua uma pesquisa interrompida: só as empresas ainda pendentes; as ambíguas continuam aguardando reconciliação."""
    obter(db, solicitante.tenant_id, solicitante, pesquisa_id)
    return executar(db, tenant_id=solicitante.tenant_id, pesquisa_id=pesquisa_id, provider=provider, graph=graph, ator_id=str(solicitante.id))


def cancelar(db: Session, *, solicitante: Solicitante, pesquisa_id: str) -> PesquisaDecisores:
    """Cancela uma prévia, ou as empresas ainda não enviadas de uma pesquisa em curso (a reserva delas é liberada). O que já foi enviado
    segue o seu desfecho normal."""
    pesquisa = obter(db, solicitante.tenant_id, solicitante, pesquisa_id)
    ator = str(solicitante.id)
    if pesquisa.estado == "criada":
        _mudar_estado(db, pesquisa, "cancelada", "cancelada_pelo_usuario", ator)
        db.commit()
        return pesquisa
    if pesquisa.estado not in ("reservada", "enviada"):
        raise PesquisaBloqueada("Esta pesquisa não pode mais ser cancelada.", "cancelamento_indisponivel")
    itens = itens_de(db, pesquisa.id)
    ja_enviou = any(i.estado not in ("pendente", "deduplicada") for i in itens)
    for item in itens:
        if item.estado == "pendente":
            _liquidar_item(db, pesquisa, item, 0, origem="cancelamento", motivo="cancelada_pelo_usuario", ator_id=ator, agora=agora_utc())
            _mudar_estado_item(db, pesquisa, item, "cancelado", "cancelada_pelo_usuario", ator)
    if not ja_enviou:
        _mudar_estado(db, pesquisa, "cancelada", "cancelada_pelo_usuario", ator)
    else:
        _finalizar(db, pesquisa, ator)
    db.commit()
    return pesquisa


def reconciliar_item(db: Session, *, pesquisa_id: str, item_id: int, creditos_consumidos: int, motivo: str, ator_id: str | None,
                     tenant_auditoria: str) -> PesquisaDecisores:
    """Fecha uma empresa de desfecho ambíguo com o consumo confirmado no painel/relatório do provedor (0 libera tudo). Administrativo."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo e a fonte da reconciliação (ex.: relatório de uso do provedor).")
    if isinstance(creditos_consumidos, bool) or not isinstance(creditos_consumidos, int) or creditos_consumidos < 0:
        raise ValidacaoFalhou("O consumo confirmado deve ser um inteiro maior ou igual a zero.")
    pesquisa = db.query(PesquisaDecisores).filter_by(id=pesquisa_id).one_or_none()
    item = db.query(PesquisaDecisoresEmpresa).filter_by(id=item_id, pesquisa_id=pesquisa_id).one_or_none() if pesquisa else None
    if pesquisa is None or item is None:
        raise NaoEncontrado("Pesquisa ou empresa não encontrada.")
    if item.estado != "ambiguo":
        raise PesquisaBloqueada("Só empresas com desfecho ambíguo podem ser reconciliadas.", "item_nao_ambiguo")
    if creditos_consumidos > item.creditos_reservados:
        raise ValidacaoFalhou(f"O consumo confirmado ({creditos_consumidos}) excede o que estava reservado ({item.creditos_reservados}).")
    _liquidar_item(db, pesquisa, item, creditos_consumidos, origem="reconciliacao", motivo=motivo.strip(), ator_id=ator_id, agora=agora_utc())
    ledger.lancar(db, pesquisa.tenant_id, "RECONCILIACAO", provedor=pesquisa.provedor, pesquisa_id=pesquisa.id, item_id=item.id,
                  origem="reconciliacao", motivo=f"consumo confirmado={creditos_consumidos}: {motivo.strip()}", ator_id=ator_id,
                  idempotency_key=f"reconciliacao:{item.id}")
    _mudar_estado_item(db, pesquisa, item, "concluido" if creditos_consumidos else "sem_resultados", f"reconciliado:{motivo.strip()}", ator_id)
    itens = itens_de(db, pesquisa.id)
    pesquisa.creditos_consumidos = sum(i.creditos_consumidos for i in itens)
    if not any(i.estado == "ambiguo" for i in itens):
        pesquisa.requer_reconciliacao = False
        if not any(i.estado in ("pendente", "enviado") for i in itens):
            _mudar_estado(db, pesquisa, "reconciliada", "todas_as_empresas_reconciliadas", ator_id)
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_reconciliado", "pesquisa_decisores_empresa", item.id, ator_id,
                                {"pesquisa_id": pesquisa.id, "tenant_alvo": pesquisa.tenant_id, "consumo_confirmado": creditos_consumidos,
                                 "motivo": motivo.strip()})
    db.commit()
    return pesquisa


def encerrar_reconciliacao(db: Session, *, pesquisa_id: str, motivo: str, ator_id: str | None, tenant_auditoria: str) -> PesquisaDecisores:
    """Limpa a sinalização de reconciliação de uma pesquisa sem empresas ambíguas (ex.: o provedor devolveu acima do limite e a diferença foi
    tratada por ajuste ou estorno). Exige motivo e fica auditado."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo.")
    pesquisa = db.query(PesquisaDecisores).filter_by(id=pesquisa_id).one_or_none()
    if pesquisa is None:
        raise NaoEncontrado("Pesquisa não encontrada.")
    if any(i.estado == "ambiguo" for i in itens_de(db, pesquisa.id)):
        raise PesquisaBloqueada("Ainda há empresa com desfecho ambíguo: reconcilie-a primeiro.", "item_ambiguo_pendente")
    pesquisa.requer_reconciliacao = False
    _registrar_transicao(db, pesquisa, pesquisa.estado, f"reconciliacao_encerrada:{motivo.strip()}", ator_id)
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_reconciliacao_encerrada", "pesquisa_decisores", 0, ator_id,
                                {"pesquisa_id": pesquisa.id, "tenant_alvo": pesquisa.tenant_id, "motivo": motivo.strip()})
    db.commit()
    return pesquisa
