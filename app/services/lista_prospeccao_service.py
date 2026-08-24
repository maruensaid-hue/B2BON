from sqlalchemy.orm import Session

from app.models.icp import ICP
from app.models.lista_prospeccao import ListaProspeccao
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def criar(
    db: Session, tenant_id: str, ator_id: str | None, nome: str, icp_id: int | None, cargos_alvo: list[str] | None
) -> ListaProspeccao:
    if icp_id is not None and db.query(ICP).filter_by(id=icp_id, tenant_id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"ICP {icp_id} não encontrado")

    lista = ListaProspeccao(
        tenant_id=tenant_id,
        nome=nome,
        icp_id=icp_id,
        cargos_alvo=cargos_alvo or None,
        criado_por_usuario_id=int(ator_id) if ator_id else None,
    )
    db.add(lista)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "lista_prospeccao_criada", "lista_prospeccao", lista.id, ator_id, {"nome": nome})
    db.commit()
    db.refresh(lista)
    return lista


def listar(db: Session, tenant_id: str) -> list[ListaProspeccao]:
    return db.query(ListaProspeccao).filter_by(tenant_id=tenant_id).order_by(ListaProspeccao.criado_em.desc()).all()


def obter(db: Session, tenant_id: str, lista_id: int) -> ListaProspeccao:
    lista = db.query(ListaProspeccao).filter_by(id=lista_id, tenant_id=tenant_id).one_or_none()
    if lista is None:
        raise NaoEncontrado(f"Lista de prospecção {lista_id} não encontrada")
    return lista
