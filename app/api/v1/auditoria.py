from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.auditoria import AuditLogSchema
from app.services import auditoria_service

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@router.get("", response_model=list[AuditLogSchema])
def consultar_auditoria(
    conta_id: int | None = None,
    canal: str | None = None,
    data_inicio: datetime | None = None,
    data_fim: datetime | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[AuditLogSchema]:
    return auditoria_service.consultar(db, tenant_id, conta_id, canal, data_inicio, data_fim)


@router.get("/exportar.csv")
def exportar_auditoria_csv(
    conta_id: int | None = None,
    canal: str | None = None,
    data_inicio: datetime | None = None,
    data_fim: datetime | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    logs = auditoria_service.consultar(db, tenant_id, conta_id, canal, data_inicio, data_fim)
    csv_conteudo = auditoria_service.exportar_csv(logs)
    return Response(
        content=csv_conteudo,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auditoria.csv"},
    )
