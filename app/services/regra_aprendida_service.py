from sqlalchemy.orm import Session

from app.models.regra_aprendida import RegraAprendida
from app.schemas.regra_aprendida import RegraAprendidaCreateSchema
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def listar(db: Session, tenant_id: str) -> list[RegraAprendida]:
    return db.query(RegraAprendida).filter_by(tenant_id=tenant_id).order_by(RegraAprendida.criado_em.desc()).all()


def _obter(db: Session, tenant_id: str, regra_id: int) -> RegraAprendida:
    regra = db.query(RegraAprendida).filter_by(id=regra_id, tenant_id=tenant_id).one_or_none()
    if regra is None:
        raise NaoEncontrado(f"Regra aprendida {regra_id} não encontrada")
    return regra


def criar(db: Session, tenant_id: str, ator_id: str | None, dados: RegraAprendidaCreateSchema) -> RegraAprendida:
    regra = RegraAprendida(
        tenant_id=tenant_id,
        icp_id=dados.icp_id,
        oferta_id=dados.oferta_id,
        canal=dados.canal,
        regra=dados.regra,
        ativa=True,
    )
    db.add(regra)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_criada", "regra_aprendida", regra.id, ator_id, {"regra": regra.regra})
    db.commit()
    db.refresh(regra)
    return regra


def atualizar(
    db: Session, tenant_id: str, ator_id: str | None, regra_id: int, dados: RegraAprendidaCreateSchema
) -> RegraAprendida:
    regra = _obter(db, tenant_id, regra_id)
    regra.icp_id = dados.icp_id
    regra.oferta_id = dados.oferta_id
    regra.canal = dados.canal
    regra.regra = dados.regra

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_atualizada", "regra_aprendida", regra.id, ator_id, {"regra": regra.regra})
    db.commit()
    db.refresh(regra)
    return regra


def ativar(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> RegraAprendida:
    regra = _obter(db, tenant_id, regra_id)
    regra.ativa = True

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_ativada", "regra_aprendida", regra.id, ator_id, {})
    db.commit()
    db.refresh(regra)
    return regra


def desativar(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> RegraAprendida:
    regra = _obter(db, tenant_id, regra_id)
    regra.ativa = False

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_desativada", "regra_aprendida", regra.id, ator_id, {})
    db.commit()
    db.refresh(regra)
    return regra


def excluir(db: Session, tenant_id: str, ator_id: str | None, regra_id: int) -> None:
    regra = _obter(db, tenant_id, regra_id)

    auditoria_service.registrar(db, tenant_id, "regra_aprendida_excluida", "regra_aprendida", regra.id, ator_id, {"regra": regra.regra})
    db.delete(regra)
    db.commit()


def regras_aplicaveis_texto(db: Session, tenant_id: str, icp_id: int | None, oferta_id: int | None, canal: str) -> str:
    """Loop de aprendizado (master prompt seções 13/14) — regras escritas
    por um humano depois de observar edição/rejeição repetida, injetadas
    no prompt de geração de toque. Escopo nulo = aplica a todos (mais
    amplo, não mais específico); sem ordenação de prioridade porque um
    texto curto por linha já basta pro volume esperado por tenant."""
    regras = (
        db.query(RegraAprendida)
        .filter(
            RegraAprendida.tenant_id == tenant_id,
            RegraAprendida.ativa.is_(True),
            (RegraAprendida.icp_id.is_(None)) | (RegraAprendida.icp_id == icp_id),
            (RegraAprendida.oferta_id.is_(None)) | (RegraAprendida.oferta_id == oferta_id),
            (RegraAprendida.canal.is_(None)) | (RegraAprendida.canal == canal),
        )
        .all()
    )
    if not regras:
        return ""
    return " Regras aprendidas com este cliente (respeite ao escrever): " + "; ".join(r.regra for r in regras) + "."
