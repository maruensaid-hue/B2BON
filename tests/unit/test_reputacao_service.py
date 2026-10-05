from app.services import reputacao_service

TENANT_ID = "tenant-teste"


def test_evento_abaixo_do_limiar_nao_pausa(db_session):
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 2)  # 2% < 5%

    saude = reputacao_service.status_saude(db_session, TENANT_ID, "email")

    assert saude["pausado"] is False


def test_evento_acima_do_limiar_pausa_e_audita(db_session):
    """E10-H2: pausa automática de cadências ao cruzar limiar crítico, com notificação."""
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 6)  # 6% >= 5%

    saude = reputacao_service.status_saude(db_session, TENANT_ID, "email")
    assert saude["pausado"] is True
    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is True

    from app.providers.plan_limits.stub import StubPlanLimitsProvider
    from app.services import auditoria_service

    eventos = {log.evento_tipo for log in auditoria_service.consultar(db_session, TENANT_ID, StubPlanLimitsProvider())}
    assert "canal_pausado_automaticamente" in eventos


def test_pausa_e_isolada_por_canal(db_session):
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 6)

    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "whatsapp") is False


def test_reativar_permite_envio_novamente(db_session):
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 6)
    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is True

    reputacao_service.reativar(db_session, TENANT_ID, "user-teste", "email")

    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is False


def test_amostra_pequena_nao_pausa_mesmo_com_taxa_alta(db_session):
    """Incidente 2026-10-05: 1 bounce em 15 envios (6,7%) pausava o canal.
    Percentual sobre volume pequeno não é sinal de reputação."""
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 14)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 1)

    saude = reputacao_service.status_saude(db_session, TENANT_ID, "email")

    assert saude["taxa_bounce"] > saude["limiar_bounce"]
    assert saude["pausado"] is False
    assert saude["amostra_minima"] == 50


def test_amostra_no_minimo_volta_a_pausar(db_session):
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 47)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 3)  # 50 tentativas, 6,4%

    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is True


def test_reativar_zera_bounce_da_janela_e_nao_repausa_no_proximo_evento(db_session):
    """Sem zerar a janela, os mesmos bounces continuavam contando e o
    próximo evento qualquer re-pausava o canal logo após a reativação."""
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 100)
    reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "bounce", 6)
    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is True

    reputacao_service.reativar(db_session, TENANT_ID, "user-teste", "email")
    saude = reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "enviado", 1)

    assert saude["bounces"] == 0
    assert saude["pausado"] is False

    from app.models.auditoria import AuditLog

    log = db_session.query(AuditLog).filter_by(tenant_id=TENANT_ID, evento_tipo="canal_reativado_manualmente").one()
    assert log.detalhes["bounces_zerados"] == 6
