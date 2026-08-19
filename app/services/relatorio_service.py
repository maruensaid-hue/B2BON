from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auditoria import AuditLog
from app.models.configuracao_relatorio import ConfiguracaoRelatorio
from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services import franquia_service, webhook_parceiro_service
from app.services.errors import ValidacaoFalhou

CADENCIAS_VALIDAS = {"diaria", "semanal", "mensal", "desativada"}
_DIAS_POR_CADENCIA = {"diaria": 1, "semanal": 7, "mensal": 30}
_DIAS_CHURN = 30


def calcular_metricas(
    db: Session,
    tenant_ids: list[str],
    periodo_inicio: datetime,
    periodo_fim: datetime,
    plan_limits: PlanLimitsProvider,
) -> dict:
    """Métricas de volumetria/billing pra Revendedor/Distribuidor/CyberFort
    (Fase 3 da hierarquia, raio-X) — `tenant_ids` já vem com o escopo
    resolvido por quem chama (própria árvore ou tudo, se super_admin).

    `churn` é `Licenca.status == "suspensa"` com `data_expiracao` há mais
    de 30 dias — o produto não tem hoje um conceito explícito de
    cancelamento (só `atualizar_licenca` manual, nunca usado assim na
    prática), então essa é a definição operacional adotada: suspenso faz
    tempo e não reativou é o proxy mais honesto disponível nos dados.
    """
    if not tenant_ids:
        return {
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "tenants_ativos_distribuidor": 0,
            "tenants_ativos_revendedor": 0,
            "tenants_ativos_cliente": 0,
            "novas_ativacoes": 0,
            "licencas_suspensas_periodo": 0,
            "licencas_suspensas_total": 0,
            "franquia_limite_total": 0,
            "franquia_usado_total": 0,
            "receita_periodo": 0.0,
            "churn_atual": 0,
        }

    tenants = db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()
    tenants_ativos_distribuidor = sum(1 for t in tenants if t.tipo == "distribuidor")
    tenants_ativos_revendedor = sum(1 for t in tenants if t.tipo == "revendedor")
    tenants_ativos_cliente = sum(1 for t in tenants if t.tipo == "cliente")

    novas_ativacoes = (
        db.query(Tenant)
        .filter(Tenant.id.in_(tenant_ids), Tenant.criado_em >= periodo_inicio, Tenant.criado_em < periodo_fim)
        .count()
    )

    licencas_suspensas_periodo = (
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id.in_(tenant_ids),
            AuditLog.evento_tipo == "licenca_suspensa_automaticamente",
            AuditLog.criado_em >= periodo_inicio,
            AuditLog.criado_em < periodo_fim,
        )
        .count()
    )

    licencas = db.query(Licenca).filter(Licenca.tenant_id.in_(tenant_ids)).all()
    licencas_suspensas_total = sum(1 for l in licencas if l.status == "suspensa")

    corte_churn = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=_DIAS_CHURN)
    churn_atual = sum(
        1 for l in licencas if l.status == "suspensa" and l.data_expiracao is not None and l.data_expiracao < corte_churn
    )

    franquia_limite_total = 0
    franquia_usado_total = 0
    for tenant_id in tenant_ids:
        franquia = franquia_service.obter_franquia(db, tenant_id, plan_limits)
        franquia_limite_total += franquia["limite"]
        franquia_usado_total += franquia["usado"]

    receita_periodo = (
        db.query(PagamentoLicenca)
        .filter(
            PagamentoLicenca.tenant_id.in_(tenant_ids),
            PagamentoLicenca.status == "aprovado",
            PagamentoLicenca.confirmado_em >= periodo_inicio,
            PagamentoLicenca.confirmado_em < periodo_fim,
        )
        .all()
    )
    receita_total = sum(p.valor for p in receita_periodo)

    return {
        "periodo_inicio": periodo_inicio,
        "periodo_fim": periodo_fim,
        "tenants_ativos_distribuidor": tenants_ativos_distribuidor,
        "tenants_ativos_revendedor": tenants_ativos_revendedor,
        "tenants_ativos_cliente": tenants_ativos_cliente,
        "novas_ativacoes": novas_ativacoes,
        "licencas_suspensas_periodo": licencas_suspensas_periodo,
        "licencas_suspensas_total": licencas_suspensas_total,
        "franquia_limite_total": franquia_limite_total,
        "franquia_usado_total": franquia_usado_total,
        "receita_periodo": receita_total,
        "churn_atual": churn_atual,
    }


def _tenant_ids_visiveis(db: Session, usuario_ou_tenant_id, papel: str | None = None) -> list[str]:
    """Import local pra evitar dependência circular (tenant_service não
    importa relatorio_service, mas o inverso topo-de-arquivo criaria
    ciclo se algum dia tenant_service precisar deste módulo)."""
    from app.services import tenant_service

    if papel == "super_admin":
        return [t.id for t in tenant_service.listar_tenants(db)]
    return [t.id for t in tenant_service.listar_subarvore(db, usuario_ou_tenant_id)]


def dashboard(db: Session, usuario: Usuario, periodo_dias: int, plan_limits: PlanLimitsProvider) -> dict:
    tenant_ids = _tenant_ids_visiveis(db, usuario.tenant_id, usuario.papel)

    agora = datetime.now(UTC).replace(tzinfo=None)
    inicio_atual = agora - timedelta(days=periodo_dias)
    inicio_anterior = agora - timedelta(days=2 * periodo_dias)

    return {
        "atual": calcular_metricas(db, tenant_ids, inicio_atual, agora, plan_limits),
        "anterior": calcular_metricas(db, tenant_ids, inicio_anterior, inicio_atual, plan_limits),
    }


def obter_configuracao(db: Session, tenant_id: str) -> ConfiguracaoRelatorio | None:
    return db.query(ConfiguracaoRelatorio).filter_by(tenant_id=tenant_id).one_or_none()


def definir_configuracao(db: Session, tenant_id: str, cadencia: str) -> ConfiguracaoRelatorio:
    if cadencia not in CADENCIAS_VALIDAS:
        raise ValidacaoFalhou(f"cadencia inválida: {cadencia!r}. Use um de {sorted(CADENCIAS_VALIDAS)}.")

    config = obter_configuracao(db, tenant_id)
    if config is None:
        config = ConfiguracaoRelatorio(tenant_id=tenant_id, cadencia=cadencia)
        db.add(config)
    else:
        config.cadencia = cadencia
    db.commit()
    db.refresh(config)
    return config


def _montar_corpo_email(metricas: dict, cadencia: str) -> str:
    return (
        f"Seu relatório {cadencia} da B2B ON — período de "
        f"{metricas['periodo_inicio']:%d/%m/%Y} a {metricas['periodo_fim']:%d/%m/%Y}:\n\n"
        f"Tenants ativos: {metricas['tenants_ativos_distribuidor']} distribuidor(es), "
        f"{metricas['tenants_ativos_revendedor']} revendedor(es), {metricas['tenants_ativos_cliente']} cliente(s)\n"
        f"Novas ativações no período: {metricas['novas_ativacoes']}\n"
        f"Licenças suspensas no período: {metricas['licencas_suspensas_periodo']} "
        f"(total suspensas hoje: {metricas['licencas_suspensas_total']})\n"
        f"Franquia: {metricas['franquia_usado_total']}/{metricas['franquia_limite_total']} contas usadas\n"
        f"Receita confirmada no período: R${metricas['receita_periodo']:.2f}\n"
        f"Tenants em churn (suspensos há mais de {_DIAS_CHURN} dias): {metricas['churn_atual']}\n"
    )


def disparar_periodicos(db: Session, email_provider: EmailProvider, plan_limits: PlanLimitsProvider) -> dict:
    """Cron entrypoint (`POST /cron/disparar-relatorios-periodicos`) — pra
    cada `ConfiguracaoRelatorio` ativa e devida, manda e-mail pros
    destinatários (admin/super_admin do tenant que configurou) e, só se o
    tenant for `tipo="distribuidor"`, enfileira o evento de webhook
    `relatorio_periodico` (Fase 2 — Revendedor/CyberFort não têm
    `AssinaturaWebhookParceiro`, mesma restrição já decidida lá)."""
    agora = datetime.now(UTC).replace(tzinfo=None)
    configs = db.query(ConfiguracaoRelatorio).filter(ConfiguracaoRelatorio.cadencia != "desativada").all()

    tenants_processados: list[str] = []
    emails_enviados = 0

    for config in configs:
        intervalo_dias = _DIAS_POR_CADENCIA[config.cadencia]
        devido = config.ultimo_envio_em is None or config.ultimo_envio_em + timedelta(days=intervalo_dias) <= agora
        if not devido:
            continue

        tenant = db.query(Tenant).filter_by(id=config.tenant_id).one_or_none()
        if tenant is None:
            continue

        destinatarios = (
            db.query(Usuario)
            .filter(Usuario.tenant_id == config.tenant_id, Usuario.papel.in_(["admin", "super_admin"]))
            .all()
        )

        for usuario in destinatarios:
            tenant_ids = _tenant_ids_visiveis(db, usuario.tenant_id, usuario.papel)
            metricas = calcular_metricas(db, tenant_ids, agora - timedelta(days=intervalo_dias), agora, plan_limits)
            corpo = _montar_corpo_email(metricas, config.cadencia)
            email_provider.enviar(
                usuario.email,
                "Seu relatório periódico B2B ON",
                corpo,
                "B2B ON",
                settings.sendgrid_remetente_email,
                usuario.tenant_id,
            )
            emails_enviados += 1

        if tenant.tipo == "distribuidor":
            metricas_tenant = calcular_metricas(
                db, _tenant_ids_visiveis(db, tenant.id), agora - timedelta(days=intervalo_dias), agora, plan_limits
            )
            payload = {
                key: (value.isoformat() if isinstance(value, datetime) else value)
                for key, value in metricas_tenant.items()
            }
            webhook_parceiro_service.enfileirar_evento(db, tenant.id, "relatorio_periodico", payload)

        config.ultimo_envio_em = agora
        tenants_processados.append(tenant.id)

    db.commit()
    return {"tenants_processados": tenants_processados, "emails_enviados": emails_enviados}
