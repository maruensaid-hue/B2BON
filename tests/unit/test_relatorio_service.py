from datetime import UTC, datetime, timedelta

import pytest

from app.models.auditoria import AuditLog
from app.models.configuracao_relatorio import ConfiguracaoRelatorio
from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import relatorio_service
from app.services.errors import ValidacaoFalhou
from tests.fakes import FakeEmailProvider

PLAN_LIMITS = StubPlanLimitsProvider(franquia_padrao=100)


def _plano(db_session) -> Plano:
    plano = Plano(nome=f"Plano {db_session.query(Plano).count() + 1}", franquia_contas_mes=100, max_usuarios=10, preco_mensal=490.0)
    db_session.add(plano)
    db_session.commit()
    return plano


def _tenant(db_session, tenant_id: str, tipo: str = "cliente", tenant_pai_id: str | None = None) -> Tenant:
    tenant = Tenant(id=tenant_id, razao_social=f"Empresa {tenant_id}", tipo=tipo, tenant_pai_id=tenant_pai_id)
    db_session.add(tenant)
    db_session.flush()
    return tenant


def test_calcular_metricas_vazio_retorna_zeros(db_session) -> None:
    metricas = relatorio_service.calcular_metricas(db_session, [], datetime.now(UTC), datetime.now(UTC), PLAN_LIMITS)

    assert metricas["tenants_ativos_cliente"] == 0
    assert metricas["receita_periodo"] == 0.0
    assert metricas["churn_atual"] == 0


def test_calcular_metricas_volumetria_por_tipo(db_session) -> None:
    _tenant(db_session, "dist-1", tipo="distribuidor")
    _tenant(db_session, "revenda-1", tipo="revendedor", tenant_pai_id="dist-1")
    _tenant(db_session, "cliente-1", tipo="cliente", tenant_pai_id="revenda-1")
    _tenant(db_session, "cliente-2", tipo="cliente", tenant_pai_id="revenda-1")
    db_session.commit()

    metricas = relatorio_service.calcular_metricas(
        db_session, ["dist-1", "revenda-1", "cliente-1", "cliente-2"], datetime.now(UTC), datetime.now(UTC), PLAN_LIMITS
    )

    assert metricas["tenants_ativos_distribuidor"] == 1
    assert metricas["tenants_ativos_revendedor"] == 1
    assert metricas["tenants_ativos_cliente"] == 2


def test_calcular_metricas_novas_ativacoes_dentro_do_periodo(db_session) -> None:
    _tenant(db_session, "novo-1")
    db_session.commit()
    agora = datetime.now(UTC).replace(tzinfo=None)

    dentro = relatorio_service.calcular_metricas(
        db_session, ["novo-1"], agora - timedelta(days=1), agora + timedelta(days=1), PLAN_LIMITS
    )
    fora = relatorio_service.calcular_metricas(
        db_session, ["novo-1"], agora - timedelta(days=10), agora - timedelta(days=5), PLAN_LIMITS
    )

    assert dentro["novas_ativacoes"] == 1
    assert fora["novas_ativacoes"] == 0


def test_calcular_metricas_licencas_suspensas_periodo_e_total(db_session) -> None:
    _tenant(db_session, "susp-1")
    plano = _plano(db_session)
    db_session.add(Licenca(tenant_id="susp-1", plano_id=plano.id, status="suspensa"))
    db_session.add(AuditLog(tenant_id="susp-1", evento_tipo="licenca_suspensa_automaticamente", entidade_tipo="licenca", entidade_id=1))
    db_session.commit()
    agora = datetime.now(UTC).replace(tzinfo=None)

    metricas = relatorio_service.calcular_metricas(
        db_session, ["susp-1"], agora - timedelta(days=1), agora + timedelta(days=1), PLAN_LIMITS
    )

    assert metricas["licencas_suspensas_periodo"] == 1
    assert metricas["licencas_suspensas_total"] == 1


def test_calcular_metricas_franquia_soma_tenants(db_session) -> None:
    _tenant(db_session, "franq-1")
    _tenant(db_session, "franq-2")
    db_session.commit()

    metricas = relatorio_service.calcular_metricas(
        db_session, ["franq-1", "franq-2"], datetime.now(UTC), datetime.now(UTC), PLAN_LIMITS
    )

    assert metricas["franquia_limite_total"] == 200  # 100 (stub) * 2 tenants
    assert metricas["franquia_usado_total"] == 0


def test_calcular_metricas_receita_periodo(db_session) -> None:
    _tenant(db_session, "rec-1")
    plano = _plano(db_session)
    agora = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(
        PagamentoLicenca(
            tenant_id="rec-1", plano_id=plano.id, preferencia_id_externo="pref-1", status="aprovado",
            valor=490.0, confirmado_em=agora,
        )
    )
    db_session.add(
        PagamentoLicenca(
            tenant_id="rec-1", plano_id=plano.id, preferencia_id_externo="pref-2", status="rejeitado",
            valor=990.0, confirmado_em=agora,
        )
    )
    db_session.commit()

    metricas = relatorio_service.calcular_metricas(
        db_session, ["rec-1"], agora - timedelta(days=1), agora + timedelta(days=1), PLAN_LIMITS
    )

    assert metricas["receita_periodo"] == 490.0  # só o aprovado conta


def test_calcular_metricas_churn_atual_suspenso_ha_mais_de_30_dias(db_session) -> None:
    _tenant(db_session, "churn-1")
    _tenant(db_session, "recem-suspenso")
    plano = _plano(db_session)
    agora = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(Licenca(tenant_id="churn-1", plano_id=plano.id, status="suspensa", data_expiracao=agora - timedelta(days=40)))
    db_session.add(Licenca(tenant_id="recem-suspenso", plano_id=plano.id, status="suspensa", data_expiracao=agora - timedelta(days=2)))
    db_session.commit()

    metricas = relatorio_service.calcular_metricas(
        db_session, ["churn-1", "recem-suspenso"], agora, agora, PLAN_LIMITS
    )

    assert metricas["churn_atual"] == 1


def test_dashboard_super_admin_ve_tudo(db_session) -> None:
    _tenant(db_session, "dashboard-a")
    _tenant(db_session, "dashboard-b")
    db_session.commit()
    super_admin = Usuario(tenant_id="dashboard-a", nome="Super", email="super@dashboard.com.br", papel="super_admin")
    db_session.add(super_admin)
    db_session.commit()

    resultado = relatorio_service.dashboard(db_session, super_admin, periodo_dias=7, plan_limits=PLAN_LIMITS)

    total_visivel = (
        resultado["atual"]["tenants_ativos_distribuidor"]
        + resultado["atual"]["tenants_ativos_revendedor"]
        + resultado["atual"]["tenants_ativos_cliente"]
    )
    assert total_visivel >= 2


def test_dashboard_distribuidor_ve_so_subarvore(db_session) -> None:
    _tenant(db_session, "dist-scope", tipo="distribuidor")
    _tenant(db_session, "revenda-scope", tipo="revendedor", tenant_pai_id="dist-scope")
    _tenant(db_session, "outro-dist", tipo="distribuidor")  # árvore irmã
    db_session.commit()
    admin = Usuario(tenant_id="dist-scope", nome="Admin", email="admin@distscope.com.br", papel="admin")
    db_session.add(admin)
    db_session.commit()

    resultado = relatorio_service.dashboard(db_session, admin, periodo_dias=7, plan_limits=PLAN_LIMITS)

    assert resultado["atual"]["tenants_ativos_distribuidor"] == 1
    assert resultado["atual"]["tenants_ativos_revendedor"] == 1


def test_definir_configuracao_cria_e_atualiza(db_session) -> None:
    criada = relatorio_service.definir_configuracao(db_session, "config-1", "semanal")
    assert criada.cadencia == "semanal"

    atualizada = relatorio_service.definir_configuracao(db_session, "config-1", "mensal")
    assert atualizada.id == criada.id
    assert atualizada.cadencia == "mensal"


def test_definir_configuracao_cadencia_invalida_falha(db_session) -> None:
    with pytest.raises(ValidacaoFalhou):
        relatorio_service.definir_configuracao(db_session, "config-2", "anual")


def test_disparar_periodicos_envia_email_e_atualiza_ultimo_envio(db_session) -> None:
    _tenant(db_session, "disparo-1", tipo="distribuidor")
    admin = Usuario(tenant_id="disparo-1", nome="Admin", email="admin@disparo1.com.br", papel="admin")
    db_session.add(admin)
    db_session.add(ConfiguracaoRelatorio(tenant_id="disparo-1", cadencia="diaria"))
    db_session.commit()

    email_provider = FakeEmailProvider()
    resultado = relatorio_service.disparar_periodicos(db_session, email_provider, PLAN_LIMITS)

    assert resultado["tenants_processados"] == ["disparo-1"]
    assert resultado["emails_enviados"] == 1
    assert email_provider.envios[0]["destinatario"] == "admin@disparo1.com.br"
    config = relatorio_service.obter_configuracao(db_session, "disparo-1")
    assert config.ultimo_envio_em is not None


def test_disparar_periodicos_nao_devido_ainda_nao_reenvia(db_session) -> None:
    _tenant(db_session, "disparo-2", tipo="distribuidor")
    db_session.add(Usuario(tenant_id="disparo-2", nome="Admin", email="admin@disparo2.com.br", papel="admin"))
    db_session.add(
        ConfiguracaoRelatorio(tenant_id="disparo-2", cadencia="semanal", ultimo_envio_em=datetime.now(UTC).replace(tzinfo=None))
    )
    db_session.commit()

    resultado = relatorio_service.disparar_periodicos(db_session, FakeEmailProvider(), PLAN_LIMITS)

    assert resultado["tenants_processados"] == []


def test_disparar_periodicos_cadencia_desativada_e_ignorada(db_session) -> None:
    _tenant(db_session, "disparo-3", tipo="distribuidor")
    db_session.add(Usuario(tenant_id="disparo-3", nome="Admin", email="admin@disparo3.com.br", papel="admin"))
    db_session.add(ConfiguracaoRelatorio(tenant_id="disparo-3", cadencia="desativada"))
    db_session.commit()

    resultado = relatorio_service.disparar_periodicos(db_session, FakeEmailProvider(), PLAN_LIMITS)

    assert resultado["tenants_processados"] == []


def test_disparar_periodicos_so_distribuidor_enfileira_webhook(db_session) -> None:
    from app.models.assinatura_webhook_parceiro import AssinaturaWebhookParceiro
    from app.models.evento_webhook_parceiro import EventoWebhookParceiro

    _tenant(db_session, "disparo-dist", tipo="distribuidor")
    db_session.add(AssinaturaWebhookParceiro(tenant_id="disparo-dist", url_callback="https://x.com.br/wh", segredo="s"))
    db_session.add(Usuario(tenant_id="disparo-dist", nome="Admin", email="admin@disparodist.com.br", papel="admin"))
    db_session.add(ConfiguracaoRelatorio(tenant_id="disparo-dist", cadencia="diaria"))

    _tenant(db_session, "disparo-revenda", tipo="revendedor")
    db_session.add(Usuario(tenant_id="disparo-revenda", nome="Admin", email="admin@disparorevenda.com.br", papel="admin"))
    db_session.add(ConfiguracaoRelatorio(tenant_id="disparo-revenda", cadencia="diaria"))
    db_session.commit()

    relatorio_service.disparar_periodicos(db_session, FakeEmailProvider(), PLAN_LIMITS)

    eventos = db_session.query(EventoWebhookParceiro).all()
    assert len(eventos) == 1
    assert eventos[0].tipo_evento == "relatorio_periodico"
