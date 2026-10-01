"""Cash-In Government (D-072): pagamentos efetivamente recebidos, por componente e em parcelas.

Booking ≠ recebimento: o contrato registra o que foi vendido; só o recebimento é Cash-In e, com o gatilho
PAYMENT_RECEIVED, só ele torna a comissão devida.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.governo import comissoes, contratos
from app.models.contrato_governo import ComponenteContratoGoverno, RecebimentoGoverno
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou


def registrar(db: Session, contrato_id: int, *, componente_id: int, valor, recebido_em: date, referencia: str | None = None,
              idempotency_key: str | None = None, ator_id: str | None = None) -> RecebimentoGoverno:
    contrato = contratos.obter(db, contrato_id)
    if idempotency_key:
        existente = db.query(RecebimentoGoverno).filter_by(contrato_id=contrato.id, idempotency_key=idempotency_key).one_or_none()
        if existente is not None:
            return existente
    componente = db.get(ComponenteContratoGoverno, componente_id)
    if componente is None or componente.contrato_id != contrato.id:
        raise NaoEncontrado(f"Componente {componente_id} não encontrado neste contrato")
    if componente.cancelado:
        raise RegraNegocioViolada("Componente cancelado não recebe pagamento.")
    valor = Decimal(str(valor)).quantize(Decimal("0.01"))
    if valor <= 0:
        raise ValidacaoFalhou("Valor recebido precisa ser positivo.")
    ja_recebido = Decimal(str(db.query(func.sum(RecebimentoGoverno.valor)).filter_by(componente_id=componente.id, estornado_em=None)
                              .scalar() or 0))
    if ja_recebido + valor > Decimal(str(componente.valor)):
        raise RegraNegocioViolada(f"Recebimento acima do valor do componente (recebido {ja_recebido}, componente {componente.valor}).")
    recebimento = RecebimentoGoverno(contrato_id=contrato.id, componente_id=componente.id, tenant_id=contrato.tenant_id, valor=valor,
                                     recebido_em=recebido_em, referencia=referencia, idempotency_key=idempotency_key, criado_por=ator_id)
    db.add(recebimento)
    db.flush()
    geradas = comissoes.reconhecer_recebimento(db, contrato, componente, recebimento)
    auditoria_service.registrar(db, contrato.tenant_id, "recebimento_governo_registrado", "recebimento_governo", recebimento.id, ator_id, {
        "contrato_id": contrato.id, "componente": componente.tipo, "valor": float(valor), "referencia": referencia,
        "comissoes": [c.valor_comissao for c in geradas], "origem": "governo"})
    db.commit()
    return recebimento


def estornar(db: Session, recebimento_id: int, motivo: str, ator_id: str | None = None) -> dict:
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo do estorno.")
    recebimento = db.get(RecebimentoGoverno, recebimento_id)
    if recebimento is None:
        raise NaoEncontrado(f"Recebimento {recebimento_id} não encontrado")
    if recebimento.estornado_em is not None:
        raise RegraNegocioViolada("Recebimento já estornado.")
    recebimento.estornado_em = datetime.now(UTC).replace(tzinfo=None)
    recebimento.motivo_estorno = motivo
    efeito = comissoes.estornar_recebimento(db, recebimento)
    auditoria_service.registrar(db, recebimento.tenant_id, "recebimento_governo_estornado", "recebimento_governo", recebimento.id, ator_id, {
        "contrato_id": recebimento.contrato_id, "valor": float(recebimento.valor), "motivo": motivo, "comissoes": efeito, "origem": "governo"})
    db.commit()
    return efeito


def listar(db: Session, contrato_id: int) -> list[dict]:
    return [{"id": r.id, "componente_id": r.componente_id, "valor": float(r.valor), "recebido_em": r.recebido_em.isoformat(),
             "referencia": r.referencia, "estornado_em": r.estornado_em.isoformat() if r.estornado_em else None,
             "motivo_estorno": r.motivo_estorno}
            for r in db.query(RecebimentoGoverno).filter_by(contrato_id=contrato_id).order_by(RecebimentoGoverno.id).all()]
