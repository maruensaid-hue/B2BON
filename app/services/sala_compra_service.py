from sqlalchemy.orm import Session

from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.sala_compra import SalaCompra
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada
from app.services.sala_corporativa_service import obter_sala


def vincular_negocio(
    db: Session, tenant_id: str, ator_id: str | None, sala_id: int, negocio_id: int, visivel_para_comprador: bool
) -> dict:
    """Buying Room (master prompt §55, Fase 5A) — vincula um `Negocio`
    real do próprio tenant a uma Sala Corporativa já existente. Só o
    tenant vendedor (dono do negócio) pode vincular; reaproveita o
    `EstagioFunil` de 5 estágios que já existe, sem criar um funil
    paralelo."""
    sala = obter_sala(db, tenant_id, sala_id)
    negocio = db.query(Negocio).filter_by(id=negocio_id, tenant_id=tenant_id).one_or_none()
    if negocio is None:
        raise NaoEncontrado(f"Negócio {negocio_id} não encontrado")

    vinculo = db.query(SalaCompra).filter_by(sala_corporativa_id=sala.id).one_or_none()
    if vinculo is None:
        vinculo = SalaCompra(
            sala_corporativa_id=sala.id,
            tenant_id_vendedor=tenant_id,
            negocio_id=negocio_id,
            visivel_para_comprador=visivel_para_comprador,
        )
        db.add(vinculo)
    else:
        if vinculo.tenant_id_vendedor != tenant_id:
            raise RegraNegocioViolada("Esta sala já tem um negócio vinculado pelo outro lado.")
        vinculo.negocio_id = negocio_id
        vinculo.visivel_para_comprador = visivel_para_comprador

    db.flush()
    auditoria_service.registrar(
        db, tenant_id, "negocio_vinculado_sala", "sala_compra", vinculo.id, ator_id, {"negocio_id": negocio_id}
    )
    db.commit()
    db.refresh(vinculo)
    return _serializar(db, tenant_id, vinculo)


def _serializar(db: Session, tenant_id: str, vinculo: SalaCompra) -> dict:
    negocio = db.query(Negocio).filter_by(id=vinculo.negocio_id).one_or_none()
    estagio = db.query(EstagioFunil).filter_by(id=negocio.estagio_id).one_or_none() if negocio else None
    return {
        "sala_corporativa_id": vinculo.sala_corporativa_id,
        "negocio_id": vinculo.negocio_id,
        "negocio_nome": negocio.nome if negocio else None,
        "estagio_nome": estagio.nome if estagio else None,
        "estagio_tipo": estagio.tipo if estagio else None,
        "visivel_para_comprador": vinculo.visivel_para_comprador,
        "e_vendedor": vinculo.tenant_id_vendedor == tenant_id,
    }


def obter_para_sala(db: Session, tenant_id: str, sala_id: int) -> dict | None:
    sala = obter_sala(db, tenant_id, sala_id)
    vinculo = db.query(SalaCompra).filter_by(sala_corporativa_id=sala.id).one_or_none()
    if vinculo is None:
        return None
    e_vendedor = vinculo.tenant_id_vendedor == tenant_id
    if not e_vendedor and not vinculo.visivel_para_comprador:
        return None
    return _serializar(db, tenant_id, vinculo)
