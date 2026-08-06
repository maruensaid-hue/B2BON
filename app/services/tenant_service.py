import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.convite_vitrine import ConviteVitrine
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import auditoria_service, auth_service, rede_social_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou


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
    """Cria a licença se o tenant ainda não tiver nenhuma (ex.: tenant
    nascido de convite-vitrine, sem `Licenca` por design — Onda H) ou
    atualiza a existente. Sem isso, não havia como transformar um tenant
    vitrine em cliente pagante pela tela de Admin: `obter_licenca`
    recusava qualquer tenant sem licença, mesmo para criar a primeira."""
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()

    if licenca is None:
        if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
            raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
        if plano_id is None:
            raise RegraNegocioViolada("Escolha um plano para criar a primeira licença deste tenant.")
        if db.query(Plano).filter_by(id=plano_id).one_or_none() is None:
            raise NaoEncontrado(f"Plano {plano_id} não encontrado")
        licenca = Licenca(
            tenant_id=tenant_id, plano_id=plano_id, status=status or "ativa", data_expiracao=data_expiracao
        )
        db.add(licenca)
        db.flush()
        auditoria_service.registrar(
            db, tenant_id, "licenca_criada", "licenca", licenca.id, ator_id, {"plano_id": plano_id, "status": licenca.status}
        )
        db.commit()
        db.refresh(licenca)
        return licenca

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


def _gerar_tenant_id(db: Session, razao_social: str) -> str:
    """Slug legível a partir da razão social — o convite-vitrine não pede
    o identificador do tenant ao usuário final, então é gerado aqui, com
    sufixo aleatório em caso de colisão (Onda H)."""
    sem_acentos = unicodedata.normalize("NFKD", razao_social).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", sem_acentos.lower()).strip("-")[:40] or "empresa"
    candidato = base
    while db.query(Tenant).filter_by(id=candidato).one_or_none() is not None:
        candidato = f"{base}-{secrets.token_hex(3)}"
    return candidato


def gerar_convite_vitrine(
    db: Session, tenant_id_origem: str, ator_id: str | None, validade_horas: int | None
) -> ConviteVitrine:
    """Qualquer usuário de um tenant já existente pode convidar uma
    empresa nova para a Rede Social (Onda H) — não exige papel admin,
    diferente do convite de usuário (`auth_service.gerar_convite`)."""
    validade_em = datetime.now(UTC) + timedelta(hours=validade_horas) if validade_horas else None
    convite = ConviteVitrine(
        tenant_id_origem=tenant_id_origem,
        codigo=secrets.token_hex(8).upper(),
        criado_por_usuario_id=int(ator_id) if ator_id else None,
        validade_em=validade_em,
    )
    db.add(convite)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id_origem, "convite_vitrine_gerado", "convite_vitrine", convite.id, ator_id, {}
    )
    db.commit()
    db.refresh(convite)
    return convite


def revogar_convite_vitrine(db: Session, tenant_id_origem: str, ator_id: str | None, codigo: str) -> ConviteVitrine:
    convite = db.query(ConviteVitrine).filter_by(tenant_id_origem=tenant_id_origem, codigo=codigo).one_or_none()
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status != "disponivel":
        raise RegraNegocioViolada("Só é possível revogar convites disponíveis.")

    convite.status = "revogado"
    auditoria_service.registrar(
        db, tenant_id_origem, "convite_vitrine_revogado", "convite_vitrine", convite.id, ator_id, {}
    )
    db.commit()
    db.refresh(convite)
    return convite


def listar_convites_vitrine(db: Session, tenant_id_origem: str) -> list[ConviteVitrine]:
    return (
        db.query(ConviteVitrine)
        .filter_by(tenant_id_origem=tenant_id_origem)
        .order_by(ConviteVitrine.id.desc())
        .all()
    )


def _validar_convite_vitrine_disponivel(
    db: Session, convite: ConviteVitrine | None, codigo: str
) -> ConviteVitrine:
    if convite is None:
        raise NaoEncontrado(f"Convite {codigo} não encontrado")
    if convite.status == "revogado":
        raise RegraNegocioViolada("Convite revogado.")
    if convite.status == "usado":
        raise RegraNegocioViolada("Convite já utilizado.")

    validade = convite.validade_em
    if validade is not None:
        if validade.tzinfo is None:
            validade = validade.replace(tzinfo=UTC)
        if validade < datetime.now(UTC):
            convite.status = "expirado"
            db.commit()
            raise RegraNegocioViolada("Convite expirado.")
    return convite


def criar_tenant_vitrine(
    db: Session,
    codigo_convite: str,
    razao_social: str,
    nome_admin: str,
    email_admin: str,
    senha_admin: str,
    aceite_termos: bool,
    cnpj: str | None = None,
) -> Usuario:
    """Aceite de convite-vitrine: cria Tenant + Usuario (papel `admin`,
    nunca `super_admin` — isso evitaria acesso a `/admin/tenants`
    cross-tenant) + Perfil de Rede Social. Deliberadamente sem Licença —
    é essa ausência que restringe a conta só à Rede Social (Onda H)."""
    if not aceite_termos:
        raise ValidacaoFalhou("É preciso aceitar a Política de Privacidade e os Termos de Uso para se cadastrar.")

    convite = db.query(ConviteVitrine).filter_by(codigo=codigo_convite).one_or_none()
    convite = _validar_convite_vitrine_disponivel(db, convite, codigo_convite)

    if db.query(Usuario).filter_by(email=email_admin).one_or_none() is not None:
        raise RegraNegocioViolada("E-mail já cadastrado.")

    tenant_id = _gerar_tenant_id(db, razao_social)
    tenant = Tenant(id=tenant_id, razao_social=razao_social, cnpj=cnpj)
    db.add(tenant)
    db.flush()

    rede_social_service.criar_perfil_inicial(db, tenant.id, razao_social)

    usuario = Usuario(
        tenant_id=tenant.id,
        nome=nome_admin,
        email=email_admin,
        senha_hash=auth_service.hash_senha(senha_admin),
        papel="admin",
        termos_aceitos_em=datetime.now(UTC),
    )
    db.add(usuario)
    db.flush()

    convite.status = "usado"
    convite.tenant_id_gerado = tenant.id

    auditoria_service.registrar(
        db,
        tenant.id,
        "tenant_vitrine_criado",
        "tenant",
        0,
        None,
        {"razao_social": razao_social, "convite_codigo": codigo_convite},
    )
    db.commit()
    db.refresh(usuario)
    return usuario
