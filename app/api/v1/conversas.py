from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_escopo_conversa_usuario, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.conversa import ConversaComTurnosSchema, ConversaResumoSchema
from app.services import qualificacao_service

router = APIRouter(prefix="/conversas", tags=["conversas"])


@router.get("", response_model=list[ConversaResumoSchema])
def listar_conversas(
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ConversaResumoSchema]:
    """Conversas com quem respondeu (roteiro de qualificação). Vendedor (papel `user`) vê só as dos próprios contatos."""
    linhas = qualificacao_service.listar_conversas(db, tenant_id, usuario.id if usuario.papel == "user" else None, status)
    return [ConversaResumoSchema(**linha) for linha in linhas]


@router.get("/{conversa_id}", response_model=ConversaComTurnosSchema, dependencies=[Depends(exigir_escopo_conversa_usuario)])
def obter_conversa(
    conversa_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConversaComTurnosSchema:
    """Conversa completa registrada na linha do tempo da conta (E5-H1)."""
    conversa, turnos = qualificacao_service.obter_com_turnos(db, tenant_id, conversa_id)
    return ConversaComTurnosSchema(conversa=conversa, turnos=turnos)
