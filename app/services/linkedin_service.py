from sqlalchemy.orm import Session

from app.models.mensagem import Mensagem
from app.models.tarefa_linkedin import TarefaLinkedin
from app.services import aprovacao_service, auditoria_service
from app.services.errors import NaoEncontrado


def listar_tarefas(db: Session, tenant_id: str, status: str | None = None) -> list[TarefaLinkedin]:
    query = db.query(TarefaLinkedin).filter_by(tenant_id=tenant_id)
    if status:
        query = query.filter_by(status=status)
    return query.all()


def marcar(db: Session, tenant_id: str, ator_id: str | None, tarefa_id: int, executada: bool) -> TarefaLinkedin:
    """Marcação de executado/ignorado realimenta a cadência (E3-H4): fecha
    o único caminho que leva um toque de LinkedIn a um estado terminal,
    já que o envio nunca é automatizado."""
    tarefa = db.query(TarefaLinkedin).filter_by(id=tarefa_id, tenant_id=tenant_id).one_or_none()
    if tarefa is None:
        raise NaoEncontrado(f"Tarefa de LinkedIn {tarefa_id} não encontrada")

    if executada:
        aprovacao_service.marcar_enviada(db, tenant_id, tarefa.mensagem_id)
        tarefa.status = "executada"
    else:
        mensagem = db.query(Mensagem).filter_by(id=tarefa.mensagem_id).one()
        mensagem.status = "cancelado"
        tarefa.status = "ignorada"

    auditoria_service.registrar(
        db,
        tenant_id,
        "tarefa_linkedin_marcada",
        "tarefa_linkedin",
        tarefa.id,
        ator_id,
        {"executada": executada},
        canal="linkedin",
    )
    db.commit()
    db.refresh(tarefa)
    return tarefa
