from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.descarte_conta import DescarteConta
from app.services import atividade_service, auditoria_service
from app.services.errors import NaoEncontrado

# Parâmetro de aprendizado do funil, não decisão comercial fechada — mesmo
# espírito de `rampa_service.limite_diario` (ajustável, não hardcoded como
# número de negócio).
LIMIAR_PADRAO_DESCARTES = 2
PENALIDADE_SCORE = 0.1


def _obter_conta(db: Session, tenant_id: str, conta_id: int) -> Conta:
    conta = db.query(Conta).filter_by(id=conta_id, tenant_id=tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {conta_id} não encontrada")
    return conta


def priorizar(db: Session, tenant_id: str, ator_id: str | None, conta_id: int) -> Conta:
    """Marca a conta como prioritária (E2-H4)."""
    conta = _obter_conta(db, tenant_id, conta_id)
    conta.status = "priorizada"

    atividade_service.registrar(
        db, tenant_id, conta_id=conta.id, tipo="sistema", descricao="Conta priorizada", ator_id=ator_id
    )
    auditoria_service.registrar(
        db, tenant_id, "conta_priorizada", "conta", conta.id, ator_id, {}, conta_id=conta.id
    )
    db.commit()
    db.refresh(conta)
    return conta


def descartar(db: Session, tenant_id: str, ator_id: str | None, conta_id: int, motivo: str) -> Conta:
    """Marca a conta como descartada com motivo obrigatório (E2-H4).

    O descarte é registrado em `DescarteConta` para alimentar o
    refinamento do score de aderência (`penalidade_para`).
    """
    conta = _obter_conta(db, tenant_id, conta_id)
    conta.status = "descartada"
    conta.motivo_descarte = motivo

    db.add(
        DescarteConta(
            tenant_id=tenant_id,
            conta_id=conta.id,
            motivo=motivo,
            cnae=conta.segmento,
            porte=conta.porte,
            uf=conta.regiao,
        )
    )

    atividade_service.registrar(
        db, tenant_id, conta_id=conta.id, tipo="sistema", descricao=f"Conta descartada — motivo: {motivo}", ator_id=ator_id
    )
    auditoria_service.registrar(
        db, tenant_id, "conta_descartada", "conta", conta.id, ator_id, {"motivo": motivo}, conta_id=conta.id
    )
    db.commit()
    db.refresh(conta)
    return conta


def penalidade_para(db: Session, tenant_id: str, cnae: str | None, porte: str | None, uf: str | None) -> float:
    """Penalidade de score para candidatos com o mesmo perfil de descartes
    repetidos (cnae, porte, uf) — "descartes alimentam o refinamento do
    score de aderência" (E2-H4)."""
    contagem = (
        db.query(DescarteConta)
        .filter_by(tenant_id=tenant_id, cnae=cnae, porte=porte, uf=uf)
        .count()
    )
    return PENALIDADE_SCORE if contagem >= LIMIAR_PADRAO_DESCARTES else 0.0
