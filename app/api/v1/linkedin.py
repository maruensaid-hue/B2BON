from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.tarefa_linkedin import MarcarTarefaLinkedinRequestSchema, TarefaLinkedinSchema
from app.services import linkedin_service

router = APIRouter(prefix="/linkedin", tags=["linkedin"])


@router.get("/tarefas", response_model=list[TarefaLinkedinSchema])
def listar_tarefas(
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[TarefaLinkedinSchema]:
    """Tarefa diária com texto copiável e atalho para o perfil (E3-H4)."""
    return linkedin_service.listar_tarefas(db, tenant_id, status)


@router.post("/tarefas/{tarefa_id}/marcar", response_model=TarefaLinkedinSchema)
def marcar_tarefa(
    tarefa_id: int,
    dados: MarcarTarefaLinkedinRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> TarefaLinkedinSchema:
    return linkedin_service.marcar(db, tenant_id, ator_id, tarefa_id, dados.executada)
