from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.perfil_empresa import PerfilEmpresa
from app.models.tenant import Tenant
from app.models.verificacao_empresa import VerificacaoEmpresa
from app.providers.account_data.receita_federal_models import CnpjEstabelecimento
from app.services import auditoria_service, rede_social_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada


def _normalizar_cnpj(cnpj: str | None) -> str | None:
    if not cnpj:
        return None
    digitos = "".join(char for char in cnpj if char.isdigit())
    return digitos or None


def _dominio_de(url_ou_email: str) -> str | None:
    """Extrai o domínio de uma URL (`https://acme.com.br/sobre`) ou de um
    e-mail (`ana@acme.com.br`) — mesma noção de domínio nos dois casos,
    pra comparar `PerfilEmpresa.site` com o e-mail de verificação."""
    texto = url_ou_email.strip().lower()
    if "@" in texto and "://" not in texto:
        dominio = texto.split("@")[-1]
    else:
        if "://" not in texto:
            texto = f"//{texto}"
        dominio = urlparse(texto).netloc
    dominio = dominio.removeprefix("www.")
    return dominio or None


def _calcular_sinais(db: Session, tenant: Tenant, perfil: PerfilEmpresa, email_verificacao: str) -> tuple[bool, bool]:
    dominio_site = _dominio_de(perfil.site) if perfil.site else None
    dominio_email = _dominio_de(email_verificacao)
    dominio_confere = dominio_site is not None and dominio_site == dominio_email

    cnpj_normalizado = _normalizar_cnpj(tenant.cnpj)
    cnpj_encontrado_receita = False
    if cnpj_normalizado is not None:
        cnpj_encontrado_receita = (
            db.query(CnpjEstabelecimento).filter_by(cnpj=cnpj_normalizado).one_or_none() is not None
        )
    return dominio_confere, cnpj_encontrado_receita


def solicitar(db: Session, tenant_id: str, ator_id: str | None, email_verificacao: str) -> VerificacaoEmpresa:
    tenant = db.query(Tenant).filter_by(id=tenant_id).one()
    perfil = rede_social_service.garantir_perfil(db, tenant_id)

    pendente_existente = (
        db.query(VerificacaoEmpresa).filter_by(tenant_id=tenant_id, status="pendente").one_or_none()
    )
    if pendente_existente is not None:
        raise RegraNegocioViolada("Já existe uma solicitação de verificação pendente para este tenant.")

    dominio_confere, cnpj_encontrado_receita = _calcular_sinais(db, tenant, perfil, email_verificacao)

    verificacao = VerificacaoEmpresa(
        tenant_id=tenant_id,
        status="pendente",
        email_verificacao=email_verificacao,
        dominio_confere=dominio_confere,
        cnpj_encontrado_receita=cnpj_encontrado_receita,
        solicitado_por=ator_id,
    )
    db.add(verificacao)
    perfil.status_verificacao = "pendente"
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "verificacao_empresa_solicitada", "verificacao_empresa", verificacao.id, ator_id,
        {"email_verificacao": email_verificacao, "dominio_confere": dominio_confere, "cnpj_encontrado_receita": cnpj_encontrado_receita},
    )
    db.commit()
    db.refresh(verificacao)
    return verificacao


def listar_pendentes(db: Session) -> list[VerificacaoEmpresa]:
    """Cross-tenant, só pra super_admin (checado na rota) — mesmo padrão
    de `admin_tenants.py`."""
    return db.query(VerificacaoEmpresa).filter_by(status="pendente").order_by(VerificacaoEmpresa.solicitado_em).all()


def revisar(
    db: Session, ator_id: str | None, verificacao_id: int, aprovar: bool, motivo_rejeicao: str | None = None
) -> VerificacaoEmpresa:
    verificacao = db.query(VerificacaoEmpresa).filter_by(id=verificacao_id).one_or_none()
    if verificacao is None:
        raise NaoEncontrado(f"Verificação {verificacao_id} não encontrada")
    if verificacao.status != "pendente":
        raise RegraNegocioViolada("Só é possível revisar solicitações pendentes.")

    verificacao.status = "aprovada" if aprovar else "rejeitada"
    verificacao.revisado_por = ator_id
    verificacao.revisado_em = datetime.now(UTC)
    verificacao.motivo_rejeicao = motivo_rejeicao if not aprovar else None

    perfil = rede_social_service.garantir_perfil(db, verificacao.tenant_id)
    perfil.status_verificacao = "verificada" if aprovar else "rejeitada"

    auditoria_service.registrar(
        db, verificacao.tenant_id, "verificacao_empresa_revisada", "verificacao_empresa", verificacao.id, ator_id,
        {"aprovar": aprovar, "motivo_rejeicao": motivo_rejeicao},
    )
    db.commit()
    db.refresh(verificacao)
    return verificacao
