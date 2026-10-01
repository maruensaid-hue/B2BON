"""Sessões de demonstração (D-082): cada acesso ao link público ganha um tenant próprio, já preenchido com dados fictícios.

- Isolamento: um tenant por sessão — vários representantes demonstram ao mesmo tempo sem um mexer nos dados do outro.
- Sem login nem senha: a sessão recebe um token marcado como demonstração, que expira junto com o tenant.
- Nada sai do ambiente: e-mail e WhatsApp do tenant de demonstração usam provedores simulados; pagamento, convites,
  credenciais, integrações e a rede de empresas (dados de clientes reais) ficam bloqueados (ver `bloqueio.py`).
- Custo limitado: créditos de IA próprios que expiram com a sessão; teto de sessões ativas e de sessões por IP/hora.
- Limpeza: sessões expiradas são apagadas (varredura do schema) a cada nova sessão e pela rotina de cron.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.creditos_ia import ConfiguracaoCreditosTenant
from app.models.licenca import Licenca
from app.models.perfil_empresa import PerfilEmpresa
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import tenant_service
from app.services.demo import semente
from app.services.errors import NaoAutorizado, RegraNegocioViolada

logger = logging.getLogger(__name__)

PLANO_DEMO = "B2B ON Demonstração"
MODULOS_DEMO = ["map", "predator", "crm", "bids", "procurement", "sourcing", "sourcing_enterprise"]
LIMPEZA_POR_CHAMADA = 5


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def e_demo(db: Session, tenant_id: str) -> bool:
    return db.query(Tenant.id).filter(Tenant.id == tenant_id, Tenant.demo_expira_em.isnot(None)).first() is not None


def _plano(db: Session) -> Plano:
    plano = db.query(Plano).filter_by(nome=PLANO_DEMO).one_or_none()
    if plano is None:
        plano = Plano(nome=PLANO_DEMO, franquia_contas_mes=200, max_usuarios=10, preco_mensal=0.0, visivel_self_service=False,
                      modulos_contratados=list(MODULOS_DEMO), categoria="suite", segmento="PRIVATE",
                      limite_enriquecimento_site_semanal=5, limite_enriquecimento_contatos_semanal=0,
                      limite_cadencias_mes=10, limite_campanhas_mes=5)
        db.add(plano)
        db.flush()
    return plano


def ativas(db: Session) -> int:
    return db.query(Tenant).filter(Tenant.demo_expira_em.isnot(None), Tenant.demo_expira_em > _agora()).count()


def purgar_expiradas(db: Session, limite: int = LIMPEZA_POR_CHAMADA) -> int:
    """Apaga até `limite` ambientes expirados (todas as tabelas do tenant e o próprio tenant)."""
    expiradas = (db.query(Tenant).filter(Tenant.demo_expira_em.isnot(None), Tenant.demo_expira_em <= _agora())
                 .order_by(Tenant.demo_expira_em).limit(limite).all())
    for tenant in expiradas:
        _apagar(db, tenant.id)
    return len(expiradas)


def _apagar(db: Session, tenant_id: str) -> None:
    db.rollback()
    tenant_service.apagar_dados(db, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    if tenant is not None:
        db.delete(tenant)
        db.commit()


def criar(db: Session) -> tuple[Usuario, datetime]:
    """Novo ambiente de demonstração; devolve o usuário da sessão (a gestora comercial fictícia) e a expiração."""
    if not settings.demo_habilitada:
        raise NaoAutorizado("A demonstração não está habilitada neste ambiente.")
    purgar_expiradas(db)
    if ativas(db) >= settings.demo_max_sessoes_ativas:
        raise RegraNegocioViolada("Muitas demonstrações abertas agora. Tente de novo em alguns minutos.")
    expira_em = _agora() + timedelta(hours=settings.demo_ttl_horas)
    tenant_id = f"demo-{secrets.token_hex(5)}"
    plano = _plano(db)
    db.add(Tenant(id=tenant_id, razao_social=semente.EMPRESA, demo_expira_em=expira_em))
    db.flush()
    db.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa", data_expiracao=expira_em))
    # Nunca aparece no diretório da rede de empresas reais.
    db.add(PerfilEmpresa(tenant_id=tenant_id, nome_exibicao=semente.EMPRESA, visivel_no_diretorio=False))
    # IA com teto: sem a franquia mensal dos módulos — só os créditos da demonstração (que expiram com ela).
    db.add(ConfiguracaoCreditosTenant(tenant_id=tenant_id, franquia_personalizada=0))
    db.commit()
    try:
        gestora = semente.semear(db, tenant_id, expira_em, settings.demo_creditos_ia)
    except Exception:
        logger.exception("Falha ao semear a demonstração %s — removendo o ambiente parcial", tenant_id)
        _apagar(db, tenant_id)
        raise
    return gestora, expira_em
