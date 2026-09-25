"""Tenant AI Wallet (Fase 15): lotes + extrato transacional.

Invariante verificado pela reconciliação: para cada tenant, a soma das
`quantidade` dos movimentos da Fase 15 (exceto CREDIT_OVERAGE, que é
dívida pós-paga fora da carteira) é igual ao DISPONÍVEL = soma dos lotes
ativos − reservas abertas. `saldo_apos` de cada movimento é esse
disponível logo depois do evento.

Toda escrita começa por `travar`, que bloqueia a linha da carteira do
tenant (`SELECT … FOR UPDATE` no Postgres): duas execuções simultâneas
nunca reservam o mesmo saldo.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.finops import comercial
from app.contexts.finops.comercial import Evento, TipoLote
from app.models.carteira_creditos import CarteiraCreditos, MovimentoCredito
from app.models.creditos_ia import ConfiguracaoCreditosTenant, ExecucaoIa, LoteCreditos
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

logger = logging.getLogger("b2bon.creditos")

EVENTOS_FASE15 = tuple(e.value for e in Evento)
_EVENTO_POR_TIPO = {
    TipoLote.SUBSCRIPTION: Evento.GRANTED, TipoLote.TOPUP: Evento.PURCHASED, TipoLote.PROMOTIONAL: Evento.PROMOTIONAL,
    TipoLote.ADJUSTMENT: Evento.ADJUSTED,
}
ZERO = Decimal(0)


def agora_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _criar_se_ausente(db: Session, novo) -> None:
    """Insere dentro de um savepoint: se outra transação criou a mesma linha
    ao mesmo tempo (primeiro uso do tenant), a unicidade barra e quem
    chamou relê a linha dela."""
    try:
        with db.begin_nested():
            db.add(novo)
    except IntegrityError:
        pass


def travar(db: Session, tenant_id: str) -> CarteiraCreditos:
    """Trava a linha da carteira (`SELECT … FOR UPDATE`): serializa reservas,
    consumos e concessões do tenant."""
    consulta = db.query(CarteiraCreditos).filter_by(tenant_id=tenant_id).with_for_update()
    carteira = consulta.one_or_none()
    if carteira is None:
        _criar_se_ausente(db, CarteiraCreditos(tenant_id=tenant_id, saldo=ZERO))
        carteira = consulta.one()
    return carteira


def configuracao(db: Session, tenant_id: str) -> ConfiguracaoCreditosTenant:
    consulta = db.query(ConfiguracaoCreditosTenant).filter_by(tenant_id=tenant_id)
    config = consulta.one_or_none()
    if config is None:
        _criar_se_ausente(db, ConfiguracaoCreditosTenant(tenant_id=tenant_id, recarga_ativa=False, excedente_ativo=False,
                                                        percentual_alerta=80, parada_rigida=True))
        config = consulta.one()
    return config


def _lotes_vigentes(db: Session, tenant_id: str, agora: datetime):
    return db.query(LoteCreditos).filter(
        LoteCreditos.tenant_id == tenant_id, LoteCreditos.status == "ATIVO",
        LoteCreditos.tipo != TipoLote.ENTERPRISE_OVERAGE,
        (LoteCreditos.expira_em.is_(None)) | (LoteCreditos.expira_em > agora),
    )


def lotes_fefo(db: Session, tenant_id: str, agora: datetime | None = None) -> list[LoteCreditos]:
    """Ordem de consumo (comercial.POLITICA_CONSUMO = FEFO): vence antes, sai antes;
    sem validade por último; empate pela prioridade do tipo, depois pelo mais antigo."""
    agora = agora or agora_utc()
    lotes = [lote for lote in _lotes_vigentes(db, tenant_id, agora).all() if _d(lote.quantidade_restante) > 0]
    return sorted(lotes, key=lambda lote: (lote.expira_em is None, lote.expira_em or agora,
                                           comercial.PRIORIDADE_TIPO.get(TipoLote(lote.tipo), 9), lote.concedido_em or agora, lote.id))


def total_lotes(db: Session, tenant_id: str, agora: datetime | None = None) -> Decimal:
    agora = agora or agora_utc()
    return _d(_lotes_vigentes(db, tenant_id, agora).with_entities(func.sum(LoteCreditos.quantidade_restante)).scalar())


def reservado(db: Session, tenant_id: str) -> Decimal:
    return _d(db.query(func.sum(ExecucaoIa.creditos_reservados)).filter_by(tenant_id=tenant_id, status="RESERVADA").scalar())


def disponivel(db: Session, tenant_id: str, agora: datetime | None = None) -> Decimal:
    return total_lotes(db, tenant_id, agora) - reservado(db, tenant_id)


def movimentar(db: Session, tenant_id: str, evento: Evento, quantidade: Decimal, *, lote: LoteCreditos | None = None,
               execucao: ExecucaoIa | None = None, receita: Decimal | None = None, descricao: str | None = None,
               ator_id: str | None = None, idempotency_key: str | None = None, faturavel: bool = False) -> MovimentoCredito:
    db.flush()
    saldo = disponivel(db, tenant_id)
    movimento = MovimentoCredito(
        tenant_id=tenant_id, tipo=evento.value, quantidade=quantidade, saldo_apos=saldo, lote_id=lote.id if lote else None,
        execucao_id=execucao.id if execucao else None, catalogo_versao=execucao.catalogo_versao if execucao else None,
        receita_brl=receita, descricao=descricao, ator_id=ator_id, idempotency_key=idempotency_key, faturavel=faturavel,
    )
    db.add(movimento)
    carteira = travar(db, tenant_id)
    carteira.saldo = total_lotes(db, tenant_id)
    carteira.atualizado_em = datetime.now(UTC)
    db.flush()
    return movimento


def conceder(db: Session, tenant_id: str, tipo: TipoLote, quantidade: Decimal | int, origem: str, *, referencia: str | None = None,
             expira_em: datetime | None = None, receita_por_credito: Decimal = ZERO, idempotency_key: str | None = None,
             ator_id: str | None = None, descricao: str | None = None) -> LoteCreditos:
    """Cria um lote (idempotente por `idempotency_key`) e o evento correspondente."""
    quantidade = _d(quantidade)
    if quantidade <= 0:
        raise ValidacaoFalhou("Quantidade de créditos deve ser positiva.")
    if idempotency_key:
        existente = db.query(LoteCreditos).filter_by(tenant_id=tenant_id, idempotency_key=idempotency_key).one_or_none()
        if existente is not None:
            return existente
    travar(db, tenant_id)
    lote = LoteCreditos(tenant_id=tenant_id, tipo=tipo.value, origem=origem, referencia=referencia, idempotency_key=idempotency_key,
                        concedido_em=agora_utc(), expira_em=expira_em, quantidade_original=quantidade, quantidade_restante=quantidade,
                        receita_por_credito_brl=receita_por_credito, status="ATIVO")
    db.add(lote)
    db.flush()
    movimentar(db, tenant_id, _EVENTO_POR_TIPO[tipo], quantidade, lote=lote, descricao=descricao or origem, ator_id=ator_id,
               idempotency_key=idempotency_key)
    return lote


def expirar_vencidos(db: Session, tenant_id: str, agora: datetime | None = None) -> Decimal:
    """Lotes vencidos com saldo viram CREDIT_EXPIRED (a validade não é igual
    para todos: assinatura vence no fim do mês, top-up em N meses)."""
    agora = agora or agora_utc()
    vencidos = db.query(LoteCreditos).filter(
        LoteCreditos.tenant_id == tenant_id, LoteCreditos.status == "ATIVO", LoteCreditos.expira_em.isnot(None),
        LoteCreditos.expira_em <= agora, LoteCreditos.tipo != TipoLote.ENTERPRISE_OVERAGE,
    ).all()
    total = ZERO
    for lote in vencidos:
        restante = _d(lote.quantidade_restante)
        lote.status = "EXPIRADO"
        lote.quantidade_restante = ZERO
        if restante > 0:
            total += restante
            movimentar(db, tenant_id, Evento.EXPIRED, -restante, lote=lote, descricao=f"Validade encerrada ({lote.tipo})",
                       idempotency_key=f"expiracao:{lote.id}")
    return total


def _modulos_do_plano(db: Session, tenant_id: str) -> tuple[list[str], int | None]:
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if licenca is None or licenca.status != "ativa":
        return [], None
    plano = db.get(Plano, licenca.plano_id)
    return (list(plano.modulos_contratados or []) if plano else []), (plano.id if plano else None)


def plano_id(db: Session, tenant_id: str) -> int | None:
    return _modulos_do_plano(db, tenant_id)[1]


def franquia_do_tenant(db: Session, tenant_id: str) -> tuple[int, list[dict]]:
    modulos, _ = _modulos_do_plano(db, tenant_id)
    config = db.query(ConfiguracaoCreditosTenant).filter_by(tenant_id=tenant_id).one_or_none()
    return comercial.franquia_mensal(modulos, config.franquia_personalizada if config else None)


def _periodo(agora: datetime) -> tuple[str, datetime]:
    inicio_proximo = (agora.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return agora.strftime("%Y-%m"), inicio_proximo


def garantir_franquia_mensal(db: Session, tenant_id: str, agora: datetime | None = None) -> LoteCreditos | None:
    """Franquia do mês (SUBSCRIPTION), concedida uma vez por período e sem
    rollover: vence no primeiro dia do mês seguinte."""
    agora = agora or agora_utc()
    total, _ = franquia_do_tenant(db, tenant_id)
    if total <= 0:
        return None
    periodo, vence = _periodo(agora)
    return conceder(db, tenant_id, TipoLote.SUBSCRIPTION, total, "FRANQUIA_MENSAL", referencia=periodo, expira_em=vence,
                    receita_por_credito=comercial.receita_por_credito_assinatura(), idempotency_key=f"franquia:{periodo}",
                    descricao=f"Franquia mensal {periodo}")


def preparar(db: Session, tenant_id: str, agora: datetime | None = None) -> CarteiraCreditos:
    """Trava a carteira, expira o vencido e garante a franquia do mês."""
    carteira = travar(db, tenant_id)
    expirar_vencidos(db, tenant_id, agora)
    garantir_franquia_mensal(db, tenant_id, agora)
    return carteira


def consumir(db: Session, tenant_id: str, quantidade: Decimal, execucao: ExecucaoIa) -> tuple[Decimal, Decimal, Decimal]:
    """Consome em FEFO. Devolve (consumido, receita, falta)."""
    restante = quantidade
    receita_total = ZERO
    for lote in lotes_fefo(db, tenant_id):
        if restante <= 0:
            break
        usar = min(restante, _d(lote.quantidade_restante))
        receita = (usar * _d(lote.receita_por_credito_brl)).quantize(Decimal("0.0001"))
        lote.quantidade_restante = _d(lote.quantidade_restante) - usar
        if _d(lote.quantidade_restante) <= 0:
            lote.status = "ESGOTADO"
        movimentar(db, tenant_id, Evento.CONSUMED, -usar, lote=lote, execucao=execucao, receita=receita,
                   descricao=execucao.workload_codigo)
        receita_total += receita
        restante -= usar
    return quantidade - restante, receita_total, restante


def lote_excedente(db: Session, tenant_id: str, agora: datetime | None = None) -> LoteCreditos:
    """Conta pós-paga do mês (Enterprise): quantidade negativa = consumo faturável."""
    periodo, _ = _periodo(agora or agora_utc())
    chave = f"excedente:{periodo}"
    lote = db.query(LoteCreditos).filter_by(tenant_id=tenant_id, idempotency_key=chave).one_or_none()
    if lote is None:
        lote = LoteCreditos(tenant_id=tenant_id, tipo=TipoLote.ENTERPRISE_OVERAGE.value, origem="EXCEDENTE_POS_PAGO", referencia=periodo,
                            idempotency_key=chave, concedido_em=agora_utc(), quantidade_original=ZERO, quantidade_restante=ZERO,
                            receita_por_credito_brl=comercial.receita_por_credito_excedente(), status="ATIVO")
        db.add(lote)
        db.flush()
    return lote


def excedente_no_mes(db: Session, tenant_id: str, agora: datetime | None = None) -> Decimal:
    periodo, _ = _periodo(agora or agora_utc())
    lote = db.query(LoteCreditos).filter_by(tenant_id=tenant_id, idempotency_key=f"excedente:{periodo}").one_or_none()
    return -_d(lote.quantidade_restante) if lote else ZERO


def estornar_consumo(db: Session, execucao: ExecucaoIa, motivo: str, ator_id: str | None = None) -> Decimal:
    """Devolve o que a execução consumiu ao lote de origem (ou a um lote de
    ajuste, se o original já venceu) e reverte o excedente."""
    devolvido = ZERO
    agora = agora_utc()
    consumos = db.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo=Evento.CONSUMED.value).all()
    for consumo in consumos:
        quantidade = -_d(consumo.quantidade)
        lote = db.get(LoteCreditos, consumo.lote_id)
        if lote is not None and (lote.expira_em is None or lote.expira_em > agora) and lote.status in ("ATIVO", "ESGOTADO"):
            lote.quantidade_restante = _d(lote.quantidade_restante) + quantidade
            lote.status = "ATIVO"
            destino = lote
        else:
            destino = LoteCreditos(tenant_id=execucao.tenant_id, tipo=TipoLote.ADJUSTMENT.value, origem="ESTORNO", referencia=execucao.id,
                                   concedido_em=agora, expira_em=None, quantidade_original=quantidade, quantidade_restante=quantidade,
                                   receita_por_credito_brl=_d(lote.receita_por_credito_brl) if lote else ZERO, status="ATIVO")
            db.add(destino)
            db.flush()
        movimentar(db, execucao.tenant_id, Evento.REFUNDED, quantidade, lote=destino, execucao=execucao,
                   receita=-_d(consumo.receita_brl), descricao=motivo, ator_id=ator_id)
        devolvido += quantidade
    for excedente in db.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo=Evento.OVERAGE.value, faturavel=True).all():
        lote = db.get(LoteCreditos, excedente.lote_id)
        if lote is not None:
            lote.quantidade_restante = _d(lote.quantidade_restante) - _d(excedente.quantidade)
        movimentar(db, execucao.tenant_id, Evento.OVERAGE, -_d(excedente.quantidade), lote=lote, execucao=execucao,
                   receita=-_d(excedente.receita_brl), descricao=f"Estorno: {motivo}", ator_id=ator_id, faturavel=True)
    return devolvido


def ajustar(db: Session, tenant_id: str, quantidade: Decimal, motivo: str, ator_id: str | None, *, tipo: TipoLote = TipoLote.ADJUSTMENT,
            expira_em: datetime | None = None) -> dict:
    """Ajuste administrativo auditado: positivo cria lote; negativo debita em FEFO."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo do ajuste.")
    preparar(db, tenant_id)
    antes = disponivel(db, tenant_id)
    if quantidade > 0:
        lote = conceder(db, tenant_id, tipo, quantidade, f"AJUSTE_ADMIN:{tipo.value}", expira_em=expira_em, ator_id=ator_id, descricao=motivo)
        referencia = lote.id
    elif quantidade < 0:
        if -quantidade > antes:
            raise ValidacaoFalhou("Débito maior que o saldo disponível.")
        restante = -quantidade
        for lote in lotes_fefo(db, tenant_id):
            if restante <= 0:
                break
            usar = min(restante, _d(lote.quantidade_restante))
            lote.quantidade_restante = _d(lote.quantidade_restante) - usar
            if _d(lote.quantidade_restante) <= 0:
                lote.status = "ESGOTADO"
            referencia = movimentar(db, tenant_id, Evento.ADJUSTED, -usar, lote=lote, descricao=motivo, ator_id=ator_id).id
            restante -= usar
    else:
        raise ValidacaoFalhou("Quantidade do ajuste não pode ser zero.")
    depois = disponivel(db, tenant_id)
    auditoria_service.registrar(db, tenant_id, "creditos_ia_ajustados", "lote_credito" if quantidade > 0 else "movimento_credito",
                                referencia, ator_id, {
        "motivo": motivo, "tipo": tipo.value, "quantidade": float(quantidade), "valor_anterior": float(antes), "valor_novo": float(depois),
    })
    db.commit()
    return {"disponivel_anterior": float(antes), "disponivel": float(depois)}


def reconciliar(db: Session, tenant_id: str) -> dict:
    """Relatório de reconciliação: extrato × lotes × reservas × espelho legado."""
    agora = agora_utc()
    soma_movimentos = _d(db.query(func.sum(MovimentoCredito.quantidade)).filter(
        MovimentoCredito.tenant_id == tenant_id, MovimentoCredito.tipo.in_(EVENTOS_FASE15),
        MovimentoCredito.tipo != Evento.OVERAGE.value).scalar())
    lotes = total_lotes(db, tenant_id, agora)
    # lotes vencidos ainda não processados contam no extrato até virarem CREDIT_EXPIRED
    pendente_expiracao = _d(db.query(func.sum(LoteCreditos.quantidade_restante)).filter(
        LoteCreditos.tenant_id == tenant_id, LoteCreditos.status == "ATIVO", LoteCreditos.expira_em.isnot(None),
        LoteCreditos.expira_em <= agora, LoteCreditos.tipo != TipoLote.ENTERPRISE_OVERAGE).scalar())
    reservas = reservado(db, tenant_id)
    esperado = lotes + pendente_expiracao - reservas
    carteira = db.query(CarteiraCreditos).filter_by(tenant_id=tenant_id).one_or_none()
    return {
        "tenant_id": tenant_id, "soma_extrato": float(soma_movimentos), "lotes_vigentes": float(lotes),
        "vencidos_a_processar": float(pendente_expiracao), "reservado": float(reservas),
        "disponivel": float(lotes - reservas), "espelho_carteira": float(_d(carteira.saldo)) if carteira else 0.0,
        "consistente": soma_movimentos == esperado,
        "diferenca": float(soma_movimentos - esperado),
    }
