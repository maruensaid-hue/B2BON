"""Execução da pesquisa de decisores: envio ao provedor, liquidação dos créditos pelo consumo MEDIDO, retomada, cancelamento e reconciliação.

Só roda depois de `pesquisa.confirmar` ter gravado a reserva. Cada empresa é registrada como `enviado` ANTES da chamada ao provedor e liquidada
(consumo + liberação do que sobrou) na mesma transação em que os decisores são gravados. O que se debita é o que a resposta do provedor informa
(`billing.creditsCharged`): nunca uma estimativa e nunca "1 contato = 1 crédito". Desfecho ambíguo (inclusive medição ausente) não é repetido
nem liberado: a reserva fica retida até a reconciliação.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import ledger, precos
from app.contexts.enriquecimento.config import PoliticaResolvida, agora_utc, obter_politica
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


def _liquidar_item(db: Session, pesquisa: PesquisaDecisores, item: PesquisaDecisoresEmpresa, medidos: int, *, origem: str, motivo: str | None,
                   ator_id: str | None, agora: datetime, politica: PoliticaResolvida | None = None) -> None:
    """Converte a reserva da empresa em consumo e libera o que sobrou. `medidos` são créditos DO PROVEDOR informados por ele. Debita do cliente
    `medidos × creditos_cliente_por_credito_provedor`, registra custo de aquisição e valor de venda (fotos da política) e libera
    `reservado − medido`. Se o provedor consumiu mais do que o reservado, o consumo real é lançado por inteiro e a pesquisa é sinalizada.
    Idempotente por item (chaves fixas no razão)."""
    if isinstance(medidos, bool) or not isinstance(medidos, int) or medidos < 0:
        raise ValueError("consumo medido inválido")
    politica = politica or obter_politica(db, pesquisa.politica_id)
    fator, reservados = politica.creditos_cliente_por_credito_provedor, item.provedor_reservados
    abatido_da_reserva = min(medidos, reservados)
    ledger.travar_carteira(db, pesquisa.tenant_id)
    if medidos > 0:
        ledger.lancar(
            db, pesquisa.tenant_id, "CONSUMO", delta_saldo=-medidos * fator, delta_reservado=-abatido_da_reserva * fator,
            provedor_delta_reservado=-abatido_da_reserva, provedor_delta_consumido=medidos, provedor=pesquisa.provedor, pesquisa_id=pesquisa.id,
            item_id=item.id, origem=origem, motivo=motivo, ator_id=ator_id, idempotency_key=f"consumo:{item.id}", agora=agora,
            custo_unitario_brl=politica.custo_unitario_brl, preco_unitario_brl=politica.preco_unitario_brl,
            custo_total_brl=precos.valor(medidos, politica.custo_unitario_brl), valor_venda_brl=precos.valor(medidos, politica.preco_unitario_brl),
            politica_id=politica.id,
        )
    if reservados > medidos:
        ledger.lancar(db, pesquisa.tenant_id, "LIBERACAO", delta_reservado=-(reservados - medidos) * fator,
                      provedor_delta_reservado=-(reservados - medidos), provedor=pesquisa.provedor, pesquisa_id=pesquisa.id, item_id=item.id,
                      origem=origem, motivo=motivo, ator_id=ator_id, idempotency_key=f"liberacao:{item.id}", agora=agora, politica_id=politica.id)
    elif medidos > reservados:
        pesquisa.requer_reconciliacao = True
        logger.error("ENRIQUECIMENTO_ACIMA_DO_RESERVADO pesquisa=%s item=%s medido=%s reservado=%s", pesquisa.id, item.id, medidos, reservados)
    item.provedor_medidos, item.creditos_consumidos = medidos, medidos * fator


def _marcar_envios_antigos_como_ambiguos(db: Session, pesquisa: PesquisaDecisores, agora: datetime) -> None:
    """Empresa 'enviada' há tempo demais sem desfecho (o processo morreu no meio): ninguém sabe se o provedor consumiu, então é ambígua."""
    corte = agora - timedelta(minutes=settings.enriquecimento_item_enviado_stale_min)
    for item in itens_de(db, pesquisa.id):
        if item.estado == "enviado" and item.enviado_em is not None and item.enviado_em <= corte:
            _mudar_estado_item(db, pesquisa, item, "ambiguo", "enviado_sem_desfecho", None)
            pesquisa.requer_reconciliacao = True


def _totais(pesquisa: PesquisaDecisores, itens: list[PesquisaDecisoresEmpresa]) -> None:
    pesquisa.creditos_consumidos = sum(i.creditos_consumidos for i in itens)
    pesquisa.provedor_consumidos = sum(i.provedor_medidos or 0 for i in itens)


def _finalizar(db: Session, pesquisa: PesquisaDecisores, ator_id: str | None) -> None:
    itens = itens_de(db, pesquisa.id)
    _totais(pesquisa, itens)
    if any(i.estado in ("pendente", "enviado") for i in itens):
        return
    if any(i.estado == "ambiguo" for i in itens):
        pesquisa.requer_reconciliacao = True
        if pesquisa.estado != "em_processamento":
            _mudar_estado(db, pesquisa, "em_processamento", "aguardando_reconciliacao: ha empresa com desfecho ambiguo", ator_id)
        return
    houve_falha = any(i.estado == "falha" for i in itens)
    houve_sucesso = any(i.estado in ("concluido", "sem_resultados", "deduplicada") for i in itens)
    novo = "concluida" if not houve_falha else ("parcial" if houve_sucesso else "falha")
    _mudar_estado(db, pesquisa, novo, f"consumidos={pesquisa.creditos_consumidos} reservados={pesquisa.creditos_reservados}", ator_id)


def _filtro_da_empresa(db: Session, tenant_id: str, conta: Conta, item: PesquisaDecisoresEmpresa, politica: PoliticaResolvida,
                       pesquisa: PesquisaDecisores) -> FiltroContatos:
    # Os dados a revelar são os que o USUÁRIO escolheu nesta pesquisa (já validados contra a política na prévia e na confirmação).
    revelar = (["emails"] if pesquisa.revelar_emails else []) + (["phones"] if pesquisa.revelar_telefones else [])
    filtro: dict = {"nome_empresa": conta.nome_fantasia or conta.nome, "dominio": conta.dominio, "cnpj": conta.cnpj,
                    "limite_contatos": item.decisores_solicitados, "tamanho_pagina": politica.tamanho_pagina_busca, "revelar": revelar}
    if conta.lista_prospeccao_id:
        lista = db.query(ListaProspeccao).filter_by(id=conta.lista_prospeccao_id, tenant_id=tenant_id).one_or_none()
        if lista is not None and lista.cargos_alvo:
            filtro["cargos_alvo"] = lista.cargos_alvo
    return FiltroContatos(**filtro)


def _medicao(provider: ContactEnrichmentProvider, resultado: ResultadoBuscaContatos, *, exige: bool) -> int | None:
    """Créditos do provedor medidos nesta consulta. Provedor sem custo não consome (0). Provedor pago sem medição: None (desfecho ambíguo),
    exceto quando `exige` é falso (falha certa antes de qualquer cobrança): aí vale 0 ou o que a etapa anterior já mediu."""
    if not provider.pago:
        return 0
    if resultado.creditos_provedor is not None:
        return resultado.creditos_provedor
    return None if exige else 0


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
    politica = obter_politica(db, pesquisa.politica_id)  # a política vigente NA CONFIRMAÇÃO (tarifas e preço da prévia revista)
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
        filtro = _filtro_da_empresa(db, tenant_id, conta, item, politica, pesquisa)

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
        medidos = _medicao(provider, resultado, exige=resultado.estado in ("ok", "sem_resultados"))
        if resultado.estado in ("ok", "sem_resultados") and medidos is None:  # provedor pago respondeu sem informar o consumo
            resultado = ResultadoBuscaContatos(estado="ambiguo", detalhe="medicao_ausente", ids_provedor=resultado.ids_provedor)
        if resultado.estado == "ok":
            novos = registrar_candidatos(db, tenant_id, conta, resultado.contatos[: item.decisores_solicitados], graph)
            item.decisores_retornados = len(resultado.contatos)
            item.decisores_com_linkedin = sum(1 for c in resultado.contatos[: item.decisores_solicitados] if getattr(c, "linkedin_url", None))
            _liquidar_item(db, pesquisa, item, medidos, origem="execucao", motivo=f"medido={medidos}", ator_id=ator_id, agora=agora_item, politica=politica)
            _mudar_estado_item(db, pesquisa, item, "concluido", f"revelados={len(resultado.contatos)} creditos_provedor={medidos}", ator_id)
            atividade_service.registrar(db, tenant_id, conta_id=conta.id, tipo="sistema",
                                        descricao=f"Pesquisa de decisores: {novos} decisor(es) novo(s) via {provider.nome_provedor}", ator_id=ator_id)
            auditoria_service.registrar(db, tenant_id, "decisores_pesquisados", "conta", conta.id, ator_id,
                                        {"pesquisa_id": pesquisa.id, "novos": novos, "creditos_provedor": medidos}, conta_id=conta.id)
            seguidas = 0
        elif resultado.estado == "sem_resultados":
            _liquidar_item(db, pesquisa, item, medidos, origem="execucao", motivo=f"sem_resultados medido={medidos}", ator_id=ator_id, agora=agora_item,
                           politica=politica)
            _mudar_estado_item(db, pesquisa, item, "sem_resultados", f"provedor_sem_resultados creditos_provedor={medidos}", ator_id)
            seguidas = 0
        elif resultado.estado == "erro_seguro":
            if (resultado.detalhe or "").endswith("sem_creditos"):
                logger.error("ENRIQUECIMENTO_PROVEDOR_SEM_CREDITOS provedor=%s pesquisa=%s: o saldo da conta no provedor acabou", provider.nome_provedor,
                             pesquisa.id)
            _liquidar_item(db, pesquisa, item, medidos or 0, origem="execucao", motivo=resultado.detalhe, ator_id=ator_id, agora=agora_item,
                           politica=politica)
            _mudar_estado_item(db, pesquisa, item, "falha", resultado.detalhe or "erro_seguro", ator_id)
            seguidas += 1
        else:  # ambiguo: a reserva fica retida até a reconciliação com o uso do provedor
            _mudar_estado_item(db, pesquisa, item, "ambiguo", f"{resultado.detalhe or 'desfecho_desconhecido'}; busca_medida={resultado.creditos_busca}",
                               ator_id)
            pesquisa.requer_reconciliacao = True
            seguidas += 1
        db.commit()

    _finalizar(db, pesquisa, ator_id)
    db.commit()
    logger.info("ENRIQUECIMENTO_EXECUCAO pesquisa=%s estado=%s creditos_provedor=%s reconciliar=%s", pesquisa.id, pesquisa.estado,
                pesquisa.provedor_consumidos, pesquisa.requer_reconciliacao)
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
    politica = obter_politica(db, pesquisa.politica_id)
    for item in itens:
        if item.estado == "pendente":
            _liquidar_item(db, pesquisa, item, 0, origem="cancelamento", motivo="cancelada_pelo_usuario", ator_id=ator, agora=agora_utc(), politica=politica)
            _mudar_estado_item(db, pesquisa, item, "cancelado", "cancelada_pelo_usuario", ator)
    if not ja_enviou:
        _totais(pesquisa, itens)
        _mudar_estado(db, pesquisa, "cancelada", "cancelada_pelo_usuario", ator)
    else:
        _finalizar(db, pesquisa, ator)
    db.commit()
    return pesquisa


def reconciliar_item(db: Session, *, pesquisa_id: str, item_id: int, creditos_provedor_consumidos: int, motivo: str, ator_id: str | None,
                     tenant_auditoria: str) -> PesquisaDecisores:
    """Fecha uma empresa de desfecho ambíguo com o consumo, em créditos do PROVEDOR, confirmado no painel/relatório dele (0 libera tudo).
    Administrativo. Se o confirmado exceder o reservado, o consumo real é lançado e a pesquisa continua sinalizada."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo e a fonte da reconciliação (ex.: relatório de uso do provedor).")
    if isinstance(creditos_provedor_consumidos, bool) or not isinstance(creditos_provedor_consumidos, int) or creditos_provedor_consumidos < 0:
        raise ValidacaoFalhou("O consumo confirmado deve ser um inteiro maior ou igual a zero.")
    pesquisa = db.query(PesquisaDecisores).filter_by(id=pesquisa_id).one_or_none()
    item = db.query(PesquisaDecisoresEmpresa).filter_by(id=item_id, pesquisa_id=pesquisa_id).one_or_none() if pesquisa else None
    if pesquisa is None or item is None:
        raise NaoEncontrado("Pesquisa ou empresa não encontrada.")
    if item.estado != "ambiguo":
        raise PesquisaBloqueada("Só empresas com desfecho ambíguo podem ser reconciliadas.", "item_nao_ambiguo")
    _liquidar_item(db, pesquisa, item, creditos_provedor_consumidos, origem="reconciliacao", motivo=motivo.strip(), ator_id=ator_id, agora=agora_utc())
    ledger.lancar(db, pesquisa.tenant_id, "RECONCILIACAO", provedor=pesquisa.provedor, pesquisa_id=pesquisa.id, item_id=item.id,
                  origem="reconciliacao", motivo=f"consumo confirmado no provedor={creditos_provedor_consumidos}: {motivo.strip()}", ator_id=ator_id,
                  idempotency_key=f"reconciliacao:{item.id}", politica_id=pesquisa.politica_id)
    _mudar_estado_item(db, pesquisa, item, "concluido" if creditos_provedor_consumidos else "sem_resultados", f"reconciliado:{motivo.strip()}", ator_id)
    itens = itens_de(db, pesquisa.id)
    _totais(pesquisa, itens)
    if not any(i.estado == "ambiguo" for i in itens):
        if pesquisa.provedor_consumidos <= pesquisa.provedor_reservados:
            pesquisa.requer_reconciliacao = False
        if not any(i.estado in ("pendente", "enviado") for i in itens):
            _mudar_estado(db, pesquisa, "reconciliada", "todas_as_empresas_reconciliadas", ator_id)
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_reconciliado", "pesquisa_decisores_empresa", item.id, ator_id,
                                {"pesquisa_id": pesquisa.id, "tenant_alvo": pesquisa.tenant_id, "consumo_confirmado_provedor": creditos_provedor_consumidos,
                                 "motivo": motivo.strip()})
    db.commit()
    return pesquisa


def encerrar_reconciliacao(db: Session, *, pesquisa_id: str, motivo: str, ator_id: str | None, tenant_auditoria: str) -> PesquisaDecisores:
    """Limpa a sinalização de reconciliação de uma pesquisa sem empresas ambíguas (ex.: o provedor consumiu acima do reservado e a diferença foi
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
