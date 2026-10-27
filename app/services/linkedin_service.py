from sqlalchemy.orm import Session

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.tarefa_linkedin import TarefaLinkedin
from app.services import aprovacao_service, atividade_service, auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada


def _enriquecer(db: Session, tenant_id: str, tarefas: list[TarefaLinkedin]) -> list[dict]:
    """Acrescenta contato, cargo e empresa a cada tarefa (consultas em lote, não uma por linha)."""
    ids_decisores = {t.decisor_id for t in tarefas}
    decisores = (
        {d.id: d for d in db.query(Decisor).filter(Decisor.tenant_id == tenant_id, Decisor.id.in_(ids_decisores)).all()} if ids_decisores else {}
    )
    ids_contas = {d.conta_id for d in decisores.values()}
    contas = {c.id: c for c in db.query(Conta).filter(Conta.tenant_id == tenant_id, Conta.id.in_(ids_contas)).all()} if ids_contas else {}
    resultado = []
    for tarefa in tarefas:
        decisor = decisores.get(tarefa.decisor_id)
        conta = contas.get(decisor.conta_id) if decisor is not None else None
        resultado.append(
            {
                "id": tarefa.id,
                "tenant_id": tarefa.tenant_id,
                "mensagem_id": tarefa.mensagem_id,
                "decisor_id": tarefa.decisor_id,
                "texto": tarefa.texto,
                "link_perfil": tarefa.link_perfil,
                "status": tarefa.status,
                "criado_em": tarefa.criado_em,
                "atualizado_em": tarefa.atualizado_em,
                "decisor_nome": decisor.nome if decisor is not None else None,
                "decisor_cargo": decisor.cargo if decisor is not None else None,
                "conta_id": conta.id if conta is not None else None,
                "conta_nome": (conta.nome_fantasia or conta.nome) if conta is not None else None,
            }
        )
    return resultado


def listar_tarefas(db: Session, tenant_id: str, status: str | None = None) -> list[dict]:
    """Fila de trabalho: as mais antigas primeiro (a que está esperando há mais tempo é a que deve sair antes)."""
    query = db.query(TarefaLinkedin).filter_by(tenant_id=tenant_id)
    if status:
        query = query.filter_by(status=status)
    return _enriquecer(db, tenant_id, query.order_by(TarefaLinkedin.criado_em, TarefaLinkedin.id).all())


def contar_pendentes(db: Session, tenant_id: str) -> int:
    return db.query(TarefaLinkedin).filter_by(tenant_id=tenant_id, status="pendente").count()


def marcar(db: Session, tenant_id: str, ator_id: str | None, tarefa_id: int, executada: bool) -> dict:
    """Marcação de executado/ignorado realimenta a cadência (E3-H4): fecha
    o único caminho que leva um toque de LinkedIn a um estado terminal,
    já que o envio nunca é automatizado. "Enviada" também entra na linha do
    tempo da conta, como os demais canais; repetir a mesma marcação (duplo
    clique) não repete o registro."""
    tarefa = db.query(TarefaLinkedin).filter_by(id=tarefa_id, tenant_id=tenant_id).one_or_none()
    if tarefa is None:
        raise NaoEncontrado(f"Tarefa de LinkedIn {tarefa_id} não encontrada")

    pedido = "executada" if executada else "ignorada"
    if tarefa.status != "pendente":
        if tarefa.status == pedido:
            return _enriquecer(db, tenant_id, [tarefa])[0]
        raise RegraNegocioViolada(f"Esta tarefa já foi marcada como {tarefa.status}.")

    if executada:
        aprovacao_service.marcar_enviada(db, tenant_id, tarefa.mensagem_id)
        tarefa.status = "executada"
        decisor = db.query(Decisor).filter_by(id=tarefa.decisor_id, tenant_id=tenant_id).one_or_none()
        if decisor is not None:
            atividade_service.registrar(
                db,
                tenant_id,
                conta_id=decisor.conta_id,
                tipo="linkedin",
                descricao=f"Mensagem de LinkedIn enviada (manual) para {decisor.nome}",
                ator_id=ator_id,
            )
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
    return _enriquecer(db, tenant_id, [tarefa])[0]
