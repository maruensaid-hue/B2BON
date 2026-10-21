"""Estorno, chargeback, cancelamento e ajuste de créditos de um pacote comprado: SEMPRE manual, com justificativa, evidência e aprovação.

Fluxo: `solicitar` (SOLICITADO) → `decidir` (APROVADO e executado, ou REJEITADO). Quem solicita não aprova (quatro olhos), a menos que o ambiente
desligue essa trava de propósito (`ENRIQUECIMENTO_ESTORNO_EXIGE_SEGUNDO_APROVADOR=false`). Aviso de reembolso ou chargeback do provedor de pagamento NÃO
dispara nada aqui: só sinaliza a compra (`pacotes._contestar`).

A execução é um lançamento COMPENSATÓRIO no razão (`ESTORNO_COMPRA`, nunca apaga ou altera o crédito original), limitado ao saldo adicional que ainda não
foi consumido nem vencido: o que já foi gasto não volta e fica registrado em `creditos_ja_consumidos`. Idempotente (`estorno-compra:<id>`): repetir a decisão,
um retry ou um callback repetido não debitam duas vezes. A devolução do dinheiro ao cliente acontece fora desta plataforma."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, ledger
from app.core.config import settings
from app.models.enriquecimento_creditos import EnriquecimentoCompra, EnriquecimentoEstornoCompra
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

logger = logging.getLogger("b2bon.enriquecimento")

TIPOS = ("ESTORNO", "CHARGEBACK", "CANCELAMENTO", "AJUSTE")


def _obter(db: Session, estorno_id: int) -> EnriquecimentoEstornoCompra:
    estorno = db.get(EnriquecimentoEstornoCompra, estorno_id)
    if estorno is None:
        raise NaoEncontrado("Pedido de estorno não encontrado.")
    return estorno


def serializar(e: EnriquecimentoEstornoCompra) -> dict:
    return {
        "id": e.id, "compra_id": e.compra_id, "tenant_id": e.tenant_id, "tipo": e.tipo, "creditos_solicitados": e.creditos_solicitados,
        "justificativa": e.justificativa, "evidencia": e.evidencia, "status": e.status, "solicitado_por": e.solicitado_por,
        "solicitado_em": e.solicitado_em, "decidido_por": e.decidido_por, "decidido_em": e.decidido_em, "motivo_decisao": e.motivo_decisao,
        "creditos_revertidos": e.creditos_revertidos, "creditos_ja_consumidos": e.creditos_ja_consumidos, "movimento_id": e.movimento_id,
    }


def listar(db: Session, status: str | None = None, limite: int = 100) -> list[dict]:
    consulta = db.query(EnriquecimentoEstornoCompra)
    if status:
        consulta = consulta.filter(EnriquecimentoEstornoCompra.status == status)
    return [serializar(e) for e in consulta.order_by(EnriquecimentoEstornoCompra.id.desc()).limit(max(1, min(limite, 500))).all()]


def solicitar(db: Session, compra_id: int, *, tipo: str, creditos: int, justificativa: str, evidencia: str, ator_id: str, tenant_auditoria: str
              ) -> EnriquecimentoEstornoCompra:
    compra = db.get(EnriquecimentoCompra, compra_id)
    if compra is None:
        raise NaoEncontrado("Compra não encontrada.")
    if compra.status != "APROVADA":
        raise ValidacaoFalhou("Só compras com pagamento aprovado e créditos concedidos podem ser estornadas.")
    if tipo not in TIPOS:
        raise ValidacaoFalhou(f"O tipo deve ser um de: {', '.join(TIPOS)}.")
    if isinstance(creditos, bool) or not isinstance(creditos, int) or creditos <= 0:
        raise ValidacaoFalhou("A quantidade de créditos deve ser um inteiro positivo.")
    if not justificativa or len(justificativa.strip()) < 10:
        raise ValidacaoFalhou("Descreva a justificativa em pelo menos 10 caracteres.")
    if not evidencia or len(evidencia.strip()) < 5:
        raise ValidacaoFalhou("Informe a evidência (protocolo, número da contestação, e-mail do cliente, comprovante).")
    abertos = db.query(EnriquecimentoEstornoCompra).filter(EnriquecimentoEstornoCompra.compra_id == compra.id,
                                                          EnriquecimentoEstornoCompra.status.in_(("SOLICITADO", "APROVADO"))).count()
    if abertos:
        raise ValidacaoFalhou("Já existe um pedido de estorno em andamento para esta compra.")
    ja_revertidos = sum(e.creditos_revertidos or 0 for e in db.query(EnriquecimentoEstornoCompra).filter_by(compra_id=compra.id, status="EXECUTADO").all())
    if creditos + ja_revertidos > compra.creditos:
        raise ValidacaoFalhou(f"A compra tem {compra.creditos} créditos e {ja_revertidos} já foram revertidos: o pedido excede o total.")
    estorno = EnriquecimentoEstornoCompra(compra_id=compra.id, tenant_id=compra.tenant_id, tipo=tipo, creditos_solicitados=creditos,
                                          justificativa=justificativa.strip(), evidencia=evidencia.strip(), status="SOLICITADO", solicitado_por=ator_id)
    db.add(estorno)
    db.flush()
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_estorno_solicitado", "enriquecimento_estorno_compra", estorno.id, ator_id,
                                {"compra_id": compra.id, "tenant_alvo": compra.tenant_id, "tipo": tipo, "creditos": creditos})
    db.commit()
    return estorno


def decidir(db: Session, estorno_id: int, *, aprovar: bool, motivo: str, ator_id: str, tenant_auditoria: str, agora: datetime | None = None
            ) -> EnriquecimentoEstornoCompra:
    estorno = _obter(db, estorno_id)
    if estorno.status == "EXECUTADO" or (estorno.status == "REJEITADO" and not aprovar):
        return estorno  # idempotente: repetir a decisão não refaz nada
    if estorno.status not in ("SOLICITADO", "APROVADO"):
        raise ValidacaoFalhou("Este pedido já foi decidido.")
    if not motivo or len(motivo.strip()) < 5:
        raise ValidacaoFalhou("Informe o motivo da decisão.")
    if settings.enriquecimento_estorno_exige_segundo_aprovador and estorno.solicitado_por == ator_id:
        raise NaoAutorizado("Quem solicitou o estorno não pode aprová-lo: peça a outro administrador.")
    agora = agora or config.agora_utc()
    estorno.decidido_por, estorno.decidido_em, estorno.motivo_decisao = ator_id, agora, motivo.strip()
    if not aprovar:
        estorno.status = "REJEITADO"
        auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_estorno_rejeitado", "enriquecimento_estorno_compra", estorno.id, ator_id,
                                    {"compra_id": estorno.compra_id, "motivo": motivo.strip()})
        db.commit()
        return estorno
    estorno.status = "APROVADO"
    db.flush()
    return _executar(db, estorno, ator_id, tenant_auditoria, agora)


def _executar(db: Session, estorno: EnriquecimentoEstornoCompra, ator_id: str, tenant_auditoria: str, agora: datetime) -> EnriquecimentoEstornoCompra:
    compra = db.get(EnriquecimentoCompra, estorno.compra_id)
    ledger.travar_carteira(db, estorno.tenant_id)
    ledger.expirar_vencidos(db, estorno.tenant_id, agora)
    comp = ledger.composicao(db, estorno.tenant_id, agora)
    revertivel = max(0, min(estorno.creditos_solicitados, comp["adicional_restante"], ledger.disponivel(db, estorno.tenant_id)))
    movimento = None
    if revertivel > 0:
        movimento = ledger.lancar(
            db, estorno.tenant_id, "ESTORNO_COMPRA", delta_saldo=-revertivel, origem="compra", expira_em=compra.expira_em, ator_id=ator_id,
            idempotency_key=f"estorno-compra:{estorno.id}", agora=agora,
            motivo=f"{estorno.tipo.capitalize()} da compra {compra.id} ({compra.pacote_codigo}): {estorno.justificativa[:120]}",
        )
        estorno.movimento_id = movimento.id
    estorno.creditos_revertidos = revertivel
    estorno.creditos_ja_consumidos = estorno.creditos_solicitados - revertivel
    estorno.status = "EXECUTADO"
    if estorno.creditos_ja_consumidos:
        logger.warning("ENRIQUECIMENTO_ESTORNO_PARCIAL estorno=%s compra=%s revertidos=%s ja_consumidos=%s", estorno.id, compra.id, revertivel,
                       estorno.creditos_ja_consumidos)
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_estorno_executado", "enriquecimento_estorno_compra", estorno.id, ator_id,
                                {"compra_id": compra.id, "tenant_alvo": estorno.tenant_id, "tipo": estorno.tipo, "solicitados": estorno.creditos_solicitados,
                                 "revertidos": revertivel, "ja_consumidos": estorno.creditos_ja_consumidos, "evidencia": estorno.evidencia})
    db.commit()
    return estorno
