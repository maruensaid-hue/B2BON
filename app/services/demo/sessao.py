"""Sessões de demonstração (D-082): cada acesso ao link público ganha um tenant próprio, já preenchido com dados fictícios.

- Isolamento: um tenant por sessão — vários representantes demonstram ao mesmo tempo sem um mexer nos dados do outro.
- Sem login nem senha: a sessão recebe um token marcado como demonstração, que expira junto com o tenant.
- Nada sai do ambiente: e-mail e WhatsApp do tenant de demonstração usam provedores simulados; pagamento, convites,
  credenciais, integrações e a rede de empresas (dados de clientes reais) ficam bloqueados (ver `bloqueio.py`).
- Custo limitado: créditos de IA próprios que expiram com a sessão; teto de sessões ativas e de sessões por IP/hora.
- Limpeza: sessões expiradas são apagadas (varredura do schema) a cada nova sessão e pela rotina de cron.
- Reserva (D-085): semear um ambiente leva ~600 consultas — em produção, 1 a 3 minutos de espera por clique. Ficam
  alguns ambientes já semeados de reserva; o clique só reivindica um (instantâneo) e outro é semeado em segundo plano.
  Reserva = tenant de demonstração com `demo_expira_em` além de agora + TTL + folga; reivindicar = trazer a expiração
  para agora + TTL. Uma reserva serve por menos de um dia (as datas fictícias são relativas à semeadura).
"""

import logging
import secrets
import threading
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
# Reserva vale TTL + VIDA_RESERVA; só é reivindicável enquanto faltar mais que TTL + FOLGA_RESERVA para vencer.
VIDA_RESERVA = timedelta(hours=24)
FOLGA_RESERVA = timedelta(hours=1)
_reabastecendo = threading.Lock()


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


def _limite_reserva() -> datetime:
    return _agora() + timedelta(hours=settings.demo_ttl_horas) + FOLGA_RESERVA


def ativas(db: Session) -> int:
    """Sessões em uso (reservas não contam)."""
    return db.query(Tenant).filter(Tenant.demo_expira_em.isnot(None), Tenant.demo_expira_em > _agora(),
                                   Tenant.demo_expira_em <= _limite_reserva()).count()


def reservas(db: Session) -> int:
    return db.query(Tenant).filter(Tenant.demo_expira_em > _limite_reserva()).count()


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
    """Ambiente de demonstração para quem clicou: reivindica uma reserva já semeada (instantâneo) ou, sem reserva,
    semeia na hora. Devolve o usuário da sessão (a gestora comercial fictícia) e a expiração. A limpeza de vencidos e a
    reposição da reserva ficam com `reabastecer` (segundo plano), fora do caminho de quem espera."""
    if not settings.demo_habilitada:
        raise NaoAutorizado("A demonstração não está habilitada neste ambiente.")
    if ativas(db) >= settings.demo_max_sessoes_ativas:
        raise RegraNegocioViolada("Muitas demonstrações abertas agora. Tente de novo em alguns minutos.")
    expira_em = _agora() + timedelta(hours=settings.demo_ttl_horas)
    reivindicada = _reivindicar(db, expira_em)
    if reivindicada is not None:
        return reivindicada, expira_em
    return _semear_novo(db, expira_em)


def _reivindicar(db: Session, expira_em: datetime) -> Usuario | None:
    # SKIP LOCKED: dois cliques simultâneos nunca levam o mesmo ambiente (no SQLite dos testes é ignorado).
    tenant = (db.query(Tenant).filter(Tenant.demo_expira_em > _limite_reserva()).order_by(Tenant.demo_expira_em)
              .with_for_update(skip_locked=True).first())
    if tenant is None:
        return None
    tenant.demo_expira_em = expira_em
    db.query(Licenca).filter_by(tenant_id=tenant.id).update({"data_expiracao": expira_em})
    gestora = db.query(Usuario).filter_by(tenant_id=tenant.id, email=semente.email_gestora(tenant.id)).one_or_none()
    if gestora is None:  # reserva corrompida: deixa vencer e semeia outra
        tenant.demo_expira_em = _agora()
        db.commit()
        return None
    db.commit()
    return gestora


def reabastecer(sessao_factory) -> dict:
    """Apaga vencidos e repõe a reserva até `demo_reservas`. Roda em segundo plano (após cada clique e na rotina
    horária), com sessão própria; um reabastecimento por processo de cada vez."""
    if sessao_factory is None or not settings.demo_habilitada or not _reabastecendo.acquire(blocking=False):
        return {"apagadas": 0, "criadas": 0}
    try:
        with sessao_factory() as db:
            apagadas = purgar_expiradas(db, limite=50)
            criadas = 0
            while reservas(db) < settings.demo_reservas and criadas < settings.demo_reservas:
                _semear_novo(db, _agora() + timedelta(hours=settings.demo_ttl_horas) + VIDA_RESERVA)
                criadas += 1
            return {"apagadas": apagadas, "criadas": criadas}
    except Exception:
        logger.exception("Falha ao reabastecer as demonstrações")
        return {"apagadas": 0, "criadas": 0}
    finally:
        _reabastecendo.release()


def _semear_novo(db: Session, expira_em: datetime) -> tuple[Usuario, datetime]:
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
