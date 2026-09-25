import secrets

from sqlalchemy.orm import Session

from app.models.link_captura_lead import LinkCapturaLead
from app.models.perfil_empresa import PerfilEmpresa
from app.services import conta_service
from app.services.errors import NaoEncontrado


def obter_ou_criar(db: Session, tenant_id: str) -> LinkCapturaLead:
    """Idempotente — cada tenant tem um único link permanente, gerado na
    primeira vez que a tela de Configuração é aberta (mesmo `secrets.
    token_hex` já usado em `ConviteVitrine`, mas sem expiração nem
    `status`: este código nunca vira "usado", pode ser submetido quantas
    vezes forem necessárias."""
    link = db.get(LinkCapturaLead, tenant_id)
    if link is not None:
        return link
    link = LinkCapturaLead(tenant_id=tenant_id, codigo=secrets.token_hex(8).upper())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def resolver_tenant_por_codigo(db: Session, codigo: str) -> str:
    link = db.query(LinkCapturaLead).filter_by(codigo=codigo).one_or_none()
    if link is None:
        raise NaoEncontrado("Link de captura de lead não encontrado.")
    return link.tenant_id


def obter_nome_exibicao(db: Session, tenant_id: str) -> str:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
    return perfil.nome_exibicao if perfil is not None else tenant_id


def criar_lead_publico(
    db: Session,
    codigo: str,
    nome_empresa: str,
    cnpj: str | None,
    nome_contato: str,
    email_contato: str,
    telefone_contato: str | None,
    cargo_contato: str | None,
) -> None:
    """Formulário público (CTA de anúncio, contato do site) — cai como
    prospect (sem Negócio) direto no CRM de quem gerou o link, mesmo
    template de `conta_service.criar_a_partir_de_convite_rede_social`."""
    tenant_id = resolver_tenant_por_codigo(db, codigo)
    conta_service.criar_a_partir_de_convite_rede_social(
        db,
        tenant_id,
        nome_empresa,
        cnpj,
        nome_contato,
        email_contato,
        telefone_contato=telefone_contato,
        cargo_contato=cargo_contato,
        origem="captura_lead_publica",
        descricao_atividade="Lead cadastrado automaticamente via link público de captura",
    )
    db.commit()
