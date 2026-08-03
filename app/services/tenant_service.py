from datetime import datetime

from sqlalchemy.orm import Session

from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auditoria_service, auth_service, rede_social_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada


def listar_planos(db: Session) -> list[Plano]:
    return db.query(Plano).order_by(Plano.preco_mensal).all()


def criar_tenant_inicial(
    db: Session,
    tenant_id: str,
    razao_social: str,
    plano_id: int,
    nome_admin: str,
    email_admin: str,
    senha_admin: str,
    cnpj: str | None = None,
) -> Usuario:
    """Bootstrap: cria Tenant + Licença ativa + primeiro usuário super_admin.

    Exposto só por script (`scripts/bootstrap_tenant.py`) — nunca por
    endpoint HTTP, para não expor uma rota de criação de tenant sem
    autenticação (Onda A).
    """
    if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is not None:
        raise RegraNegocioViolada(f"Tenant {tenant_id} já existe.")
    if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
        raise NaoEncontrado(f"Plano {plano_id} não encontrado")
    if db.query(Usuario).filter_by(email=email_admin).one_or_none() is not None:
        raise RegraNegocioViolada("E-mail já cadastrado.")

    tenant = Tenant(id=tenant_id, razao_social=razao_social, cnpj=cnpj)
    db.add(tenant)
    db.flush()

    licenca = Licenca(tenant_id=tenant.id, plano_id=plano_id, status="ativa")
    db.add(licenca)

    rede_social_service.criar_perfil_inicial(db, tenant.id, razao_social)

    usuario = Usuario(
        tenant_id=tenant.id,
        nome=nome_admin,
        email=email_admin,
        senha_hash=auth_service.hash_senha(senha_admin),
        papel="super_admin",
    )
    db.add(usuario)
    db.flush()

    auditoria_service.registrar(
        db, tenant.id, "tenant_criado", "tenant", 0, None, {"razao_social": razao_social}
    )
    db.commit()
    db.refresh(usuario)
    return usuario


def listar_tenants(db: Session) -> list[Tenant]:
    """Visão cross-tenant — só para super_admin (Onda A)."""
    return db.query(Tenant).order_by(Tenant.id).all()


def obter_licenca(db: Session, tenant_id: str) -> Licenca:
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if licenca is None:
        raise NaoEncontrado(f"Licença do tenant {tenant_id} não encontrada")
    return licenca


def atualizar_licenca(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    plano_id: int | None,
    status: str | None,
    data_expiracao: datetime | None,
) -> Licenca:
    licenca = obter_licenca(db, tenant_id)
    if plano_id is not None:
        if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
            raise NaoEncontrado(f"Plano {plano_id} não encontrado")
        licenca.plano_id = plano_id
    if status is not None:
        licenca.status = status
    if data_expiracao is not None:
        licenca.data_expiracao = data_expiracao

    auditoria_service.registrar(
        db,
        tenant_id,
        "licenca_atualizada",
        "licenca",
        licenca.id,
        ator_id,
        {"plano_id": plano_id, "status": status},
    )
    db.commit()
    db.refresh(licenca)
    return licenca
