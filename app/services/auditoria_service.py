import csv
import io
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.auditoria import AuditLog

# Convenção para eventos que documentam o módulo como um todo, não um
# assinante específico (ex.: ROPA — E9-H1).
TENANT_PLATAFORMA = "plataforma"


def registrar(
    db: Session,
    tenant_id: str,
    evento_tipo: str,
    entidade_tipo: str,
    entidade_id: int,
    ator_id: str | None = None,
    detalhes: dict | None = None,
    conta_id: int | None = None,
    canal: str | None = None,
) -> AuditLog:
    log = AuditLog(
        tenant_id=tenant_id,
        evento_tipo=evento_tipo,
        entidade_tipo=entidade_tipo,
        entidade_id=entidade_id,
        ator_id=ator_id,
        conta_id=conta_id,
        canal=canal,
        detalhes=detalhes or {},
    )
    db.add(log)
    db.flush()
    return log


def consultar(
    db: Session,
    tenant_id: str,
    conta_id: int | None = None,
    canal: str | None = None,
    data_inicio: datetime | None = None,
    data_fim: datetime | None = None,
) -> list[AuditLog]:
    query = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)
    if conta_id is not None:
        query = query.filter(AuditLog.conta_id == conta_id)
    if canal is not None:
        query = query.filter(AuditLog.canal == canal)
    if data_inicio is not None:
        query = query.filter(AuditLog.criado_em >= data_inicio)
    if data_fim is not None:
        query = query.filter(AuditLog.criado_em <= data_fim)
    return query.order_by(AuditLog.criado_em.desc()).all()


def exportar_csv(logs: list[AuditLog]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "tenant_id",
            "evento_tipo",
            "entidade_tipo",
            "entidade_id",
            "ator_id",
            "conta_id",
            "canal",
            "criado_em",
        ]
    )
    for log in logs:
        writer.writerow(
            [
                log.id,
                log.tenant_id,
                log.evento_tipo,
                log.entidade_tipo,
                log.entidade_id,
                log.ator_id,
                log.conta_id,
                log.canal,
                log.criado_em.isoformat(),
            ]
        )
    return buffer.getvalue()
