"""Credit Engine + Tenant Wallet (Fase 5, §55–§56).

Créditos representam workload econômico (custo), nunca "tokens". A taxa
`creditos_por_usd` é decisão comercial: com a política em
`PENDING_DEFINITION`, `creditos_para` devolve `None` e nada é debitado
(o custo continua medido). Carteira compartilhada pelo tenant, extrato
imutável com `saldo_apos`.
"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.carteira_creditos import CarteiraCreditos, MovimentoCredito
from app.models.politica_creditos_ia import PoliticaCreditosIa
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

STATUS_ATIVA = "ATIVA"
STATUS_PENDENTE = "PENDING_DEFINITION"


def politica_vigente(db: Session) -> PoliticaCreditosIa | None:
    return db.query(PoliticaCreditosIa).order_by(PoliticaCreditosIa.vigente_desde.desc(), PoliticaCreditosIa.id.desc()).first()


def creditos_para(custo_usd: Decimal | None, politica: PoliticaCreditosIa | None) -> Decimal | None:
    if custo_usd is None or politica is None or politica.status != STATUS_ATIVA or politica.creditos_por_usd is None:
        return None
    return (Decimal(custo_usd) * Decimal(str(politica.creditos_por_usd))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def definir_politica(db: Session, ator_id: str | None, creditos_por_usd: float, permite_excedente: bool, exige_saldo: bool, observacao: str | None) -> PoliticaCreditosIa:
    """Só super_admin (rota). Nova linha: o histórico de conversão fica preservado."""
    if creditos_por_usd <= 0:
        raise ValidacaoFalhou("creditos_por_usd deve ser positivo.")
    politica = PoliticaCreditosIa(
        status=STATUS_ATIVA, creditos_por_usd=creditos_por_usd, permite_excedente=permite_excedente,
        exige_saldo=exige_saldo, observacao=observacao, vigente_desde=datetime.now(UTC),
    )
    db.add(politica)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "politica_creditos_definida", "politica_creditos_ia", politica.id, ator_id,
                                {"creditos_por_usd": creditos_por_usd, "permite_excedente": permite_excedente, "exige_saldo": exige_saldo})
    db.commit()
    db.refresh(politica)
    return politica


def _carteira(db: Session, tenant_id: str) -> CarteiraCreditos:
    carteira = db.query(CarteiraCreditos).filter_by(tenant_id=tenant_id).with_for_update().one_or_none()
    if carteira is None:
        carteira = CarteiraCreditos(tenant_id=tenant_id, saldo=Decimal(0))
        db.add(carteira)
        db.flush()
    return carteira


def saldo(db: Session, tenant_id: str) -> Decimal:
    carteira = db.query(CarteiraCreditos).filter_by(tenant_id=tenant_id).one_or_none()
    return Decimal(str(carteira.saldo)) if carteira else Decimal(0)


def _movimentar(db: Session, tenant_id: str, tipo: str, quantidade: Decimal, *, registro_uso_ia_id: int | None = None,
                descricao: str | None = None, ator_id: str | None = None) -> MovimentoCredito:
    carteira = _carteira(db, tenant_id)
    novo_saldo = Decimal(str(carteira.saldo)) + quantidade
    carteira.saldo = novo_saldo
    carteira.atualizado_em = datetime.now(UTC)
    movimento = MovimentoCredito(tenant_id=tenant_id, tipo=tipo, quantidade=quantidade, saldo_apos=novo_saldo,
                                 registro_uso_ia_id=registro_uso_ia_id, descricao=descricao, ator_id=ator_id)
    db.add(movimento)
    db.flush()
    return movimento


def alocar(db: Session, tenant_id: str, quantidade: float, ator_id: str | None, descricao: str | None) -> MovimentoCredito:
    if quantidade <= 0:
        raise ValidacaoFalhou("Quantidade de créditos deve ser positiva.")
    movimento = _movimentar(db, tenant_id, "ALOCACAO", Decimal(str(quantidade)), descricao=descricao, ator_id=ator_id)
    auditoria_service.registrar(db, tenant_id, "creditos_alocados", "movimento_credito", movimento.id, ator_id, {"quantidade": quantidade})
    db.commit()
    return movimento


def debitar_consumo(db: Session, tenant_id: str, creditos: Decimal, registro_uso_ia_id: int, permite_excedente: bool) -> MovimentoCredito:
    """Chamado pelo gateway, na MESMA sessão/transação que grava o ledger.
    Consumo que deixa o saldo negativo vira `EXCEDENTE` (base de overage)."""
    saldo_atual = saldo(db, tenant_id)
    tipo = "CONSUMO" if saldo_atual >= creditos or not permite_excedente else "EXCEDENTE"
    return _movimentar(db, tenant_id, tipo, -creditos, registro_uso_ia_id=registro_uso_ia_id)


def extrato(db: Session, tenant_id: str, limite: int = 100) -> list[MovimentoCredito]:
    return db.query(MovimentoCredito).filter_by(tenant_id=tenant_id).order_by(MovimentoCredito.id.desc()).limit(limite).all()
