from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.conexao_linkedin import (
    ImportarConexoesLinkedinRequestSchema,
    ImportarConexoesLinkedinResponseSchema,
    StatusConexoesLinkedinSchema,
)
from app.schemas.tarefa_linkedin import MarcarTarefaLinkedinRequestSchema, TarefaLinkedinSchema
from app.services import linkedin_conexao_service, linkedin_service

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


@router.post("/conexoes/importar", response_model=ImportarConexoesLinkedinResponseSchema)
def importar_conexoes(
    dados: ImportarConexoesLinkedinRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ImportarConexoesLinkedinResponseSchema:
    """Upload do CSV oficial de conexões do LinkedIn (export próprio do
    usuário) — nunca automatiza login/scraping na plataforma."""
    total = linkedin_conexao_service.importar_csv(db, usuario.tenant_id, usuario.id, dados.conteudo_csv)
    return ImportarConexoesLinkedinResponseSchema(total_importado=total)


@router.get("/conexoes/status", response_model=StatusConexoesLinkedinSchema)
def status_conexoes(
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> StatusConexoesLinkedinSchema:
    return StatusConexoesLinkedinSchema(**linkedin_conexao_service.status(db, usuario.tenant_id, usuario.id))
