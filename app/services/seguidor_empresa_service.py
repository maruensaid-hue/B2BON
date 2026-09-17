from sqlalchemy.orm import Session

from app.models.seguidor_empresa import SeguidorEmpresa
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou


def esta_seguindo(db: Session, tenant_id_seguidor: str, tenant_id_seguido: str) -> bool:
    return (
        db.query(SeguidorEmpresa)
        .filter_by(tenant_id_seguidor=tenant_id_seguidor, tenant_id_seguido=tenant_id_seguido)
        .one_or_none()
        is not None
    )


def seguir(db: Session, tenant_id_seguidor: str, ator_id: str | None, tenant_id_seguido: str) -> SeguidorEmpresa:
    if tenant_id_seguidor == tenant_id_seguido:
        raise ValidacaoFalhou("Não é possível seguir o próprio tenant.")
    existente = (
        db.query(SeguidorEmpresa)
        .filter_by(tenant_id_seguidor=tenant_id_seguidor, tenant_id_seguido=tenant_id_seguido)
        .one_or_none()
    )
    if existente is not None:
        return existente

    seguidor = SeguidorEmpresa(tenant_id_seguidor=tenant_id_seguidor, tenant_id_seguido=tenant_id_seguido)
    db.add(seguidor)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_seguidor, "empresa_seguida", "seguidor_empresa", seguidor.id, ator_id,
        {"tenant_id_seguido": tenant_id_seguido},
    )
    db.commit()
    db.refresh(seguidor)
    return seguidor


def deixar_de_seguir(db: Session, tenant_id_seguidor: str, ator_id: str | None, tenant_id_seguido: str) -> None:
    seguidor = (
        db.query(SeguidorEmpresa)
        .filter_by(tenant_id_seguidor=tenant_id_seguidor, tenant_id_seguido=tenant_id_seguido)
        .one_or_none()
    )
    if seguidor is None:
        return  # idempotente — já não seguia

    auditoria_service.registrar(
        db, tenant_id_seguidor, "empresa_deixou_de_seguir", "seguidor_empresa", seguidor.id, ator_id,
        {"tenant_id_seguido": tenant_id_seguido},
    )
    db.delete(seguidor)
    db.commit()


def seguidores_de(db: Session, tenant_id_seguido: str) -> list[str]:
    linhas = db.query(SeguidorEmpresa).filter_by(tenant_id_seguido=tenant_id_seguido).all()
    return [linha.tenant_id_seguidor for linha in linhas]


def seguindo(db: Session, tenant_id_seguidor: str) -> list[str]:
    linhas = db.query(SeguidorEmpresa).filter_by(tenant_id_seguidor=tenant_id_seguidor).all()
    return [linha.tenant_id_seguido for linha in linhas]
