from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.conversa import ConversaComTurnosSchema
from app.services import qualificacao_service

router = APIRouter(prefix="/conversas", tags=["conversas"])


@router.get("/{conversa_id}", response_model=ConversaComTurnosSchema)
def obter_conversa(
    conversa_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConversaComTurnosSchema:
    """Conversa completa registrada na linha do tempo da conta (E5-H1)."""
    conversa, turnos = qualificacao_service.obter_com_turnos(db, tenant_id, conversa_id)
    return ConversaComTurnosSchema(conversa=conversa, turnos=turnos)
