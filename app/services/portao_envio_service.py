"""Aplica a checagem determinística de `predator.portao_envio` com os dados do tenant: quais domínios são "seus" numa mensagem."""

from sqlalchemy.orm import Session

from app.contexts.predator import contract as predator_contract
from app.core.config import settings
from app.models.conta import Conta
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.configuracao_email_api import ConfiguracaoEmailApi
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.perfil_empresa import PerfilEmpresa


def _dominio_do_email(email: str | None) -> str | None:
    return email.rsplit("@", 1)[1].lower() if email and "@" in email else None


def dominios_permitidos(db: Session, tenant_id: str, decisor: Decisor | None) -> set[str]:
    """Domínios do remetente (configuração de envio, e-mail por API, site do perfil da empresa), da plataforma (link de descadastro)
    e do destinatário (o site da empresa dele e o domínio do e-mail dele)."""
    dominios: set[str] = set()
    for (email,) in db.query(ConfiguracaoEnvio.remetente_email).filter_by(tenant_id=tenant_id).all():
        dominios.add(_dominio_do_email(email))
    for (email,) in db.query(ConfiguracaoEmailApi.remetente_email).filter_by(tenant_id=tenant_id).all():
        dominios.add(_dominio_do_email(email))
    for (site,) in db.query(PerfilEmpresa.site).filter_by(tenant_id=tenant_id).all():
        dominios.add(site)
    dominios.add(settings.url_base_api)
    for (link,) in db.query(ConfiguracaoComunicacao.link_agendamento).filter_by(tenant_id=tenant_id).all():
        dominios.add(link)
    if decisor is not None:
        dominios.add(_dominio_do_email(decisor.email))
        conta = db.query(Conta.dominio).filter_by(id=decisor.conta_id, tenant_id=tenant_id).one_or_none()
        if conta is not None:
            dominios.add(conta.dominio)
    return {d for d in dominios if d}


def problemas(db: Session, tenant_id: str, mensagem: Mensagem, decisor: Decisor | None) -> list:
    return predator_contract.portao_envio.verificar(
        mensagem.conteudo, mensagem.assunto, mensagem.canal, dominios_permitidos(db, tenant_id, decisor)
    )
