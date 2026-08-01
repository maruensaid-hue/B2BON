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

    from app.services import auditoria_service

    eventos = {log.evento_tipo for log in auditoria_service.consultar(db_session, TENANT_ID)}
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
