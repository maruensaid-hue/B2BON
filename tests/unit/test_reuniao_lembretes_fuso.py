"""Sentry 2026-10-02: `horario_confirmado` volta do Postgres sem fuso e a subtração com `datetime.now(UTC)` estourava
TypeError, derrubando o cron de retorno do tenant inteiro."""

from datetime import UTC, datetime, timedelta

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.reuniao import Reuniao
from app.models.tenant import Tenant
from app.providers.channels.email.stub import StubEmailProvider
from app.providers.channels.whatsapp.stub import StubWhatsAppProvider
from app.services import reuniao_service


def test_lembrete_d1_com_horario_sem_fuso(db_session):
    db_session.add(Tenant(id="t-fuso", razao_social="Fuso"))
    conta = Conta(tenant_id="t-fuso", nome="Conta", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id="t-fuso", conta_id=conta.id, nome="Ana", email="ana@exemplo.com")
    db_session.add(decisor)
    db_session.flush()
    amanha_sem_fuso = (datetime.now(UTC) + timedelta(hours=24)).replace(tzinfo=None)
    reuniao = Reuniao(tenant_id="t-fuso", conta_id=conta.id, decisor_id=decisor.id, status="agendada", vendedor_id="1",
                      data_hora=amanha_sem_fuso,
                      horario_confirmado=amanha_sem_fuso)
    db_session.add(reuniao)
    db_session.commit()

    resultado = reuniao_service.processar_lembretes(db_session, "t-fuso", StubWhatsAppProvider(), StubEmailProvider())

    assert resultado["lembretes_d1_enviados"] == 1
