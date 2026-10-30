"""E-mail registrado como inexistente (voltou como não entregue): barrado em toda a plataforma, não só nas campanhas."""

from datetime import UTC, datetime


from app.models.campanha import Campanha, CampanhaDestinatario
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import campanha_service, cadencia_service, envio_service
from tests.fakes import FakeEmailProvider, FakeWhatsAppProvider

TENANT_ID = "tenant-teste"
URL = "/api/v1/relatorio-entrega/bounces-manuais"

_TOQUES = [  # a cadência exige a composição completa (só 1 toque de WhatsApp)
    {"ordem": 1, "canal": "email", "intervalo_dias_apos_anterior": 0},
    {"ordem": 2, "canal": "whatsapp", "intervalo_dias_apos_anterior": 1, "template_whatsapp_id": "x"},
    {"ordem": 3, "canal": "email", "intervalo_dias_apos_anterior": 1},
    {"ordem": 4, "canal": "email", "intervalo_dias_apos_anterior": 1},
    {"ordem": 5, "canal": "linkedin", "intervalo_dias_apos_anterior": 1},
]


class _RelogioFixo:
    _agora = datetime(2024, 1, 8, 14, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._agora


def _campanha(db_session, canais=("email",), template=None) -> Campanha:
    campanha = campanha_service.criar(
        db_session, TENANT_ID, None, "Campanha", "marketing", list(canais), "Assunto", "Corpo", template, StubPlanLimitsProvider()
    )
    return campanha


def _destinatario(db_session, campanha_id: int, email: str, status: str, telefone: str | None = None) -> CampanhaDestinatario:
    destinatario = CampanhaDestinatario(
        tenant_id=TENANT_ID, campanha_id=campanha_id, nome="Fulano", email=email, telefone=telefone, status=status
    )
    db_session.add(destinatario)
    db_session.commit()
    return destinatario


def test_destinatario_que_falhou_na_hora_tambem_e_registrado_e_para_de_voltar_a_fila(client, onboarding_completo, db_session):
    """Um SMTP que recusa o endereço na hora deixa o destinatário `falhou`, que a retentativa reenviaria."""
    campanha = _campanha(db_session)
    falhou = _destinatario(db_session, campanha.id, "  Errado@Empresa.com  ", "falhou")  # com espaços e maiúsculas, como pode vir de planilha

    corpo = client.post(URL, json={"texto": "errado@empresa.com"}).json()

    assert corpo["registrados"] == ["errado@empresa.com"] and corpo["nao_encontrados"] == []
    db_session.refresh(falhou)
    assert falhou.bounce_em is not None
    bloqueios = client.get("/api/v1/bloqueios-contato").json()
    assert [(b["email"], b["origem"]) for b in bloqueios] == [("errado@empresa.com", "email_inexistente")]
    assert bloqueios[0]["telefone"] is None


def test_endereco_pendente_em_outra_campanha_nao_e_enviado(client, onboarding_completo, db_session):
    primeira = _campanha(db_session)
    _destinatario(db_session, primeira.id, "voltou@empresa.com", "enviado")
    client.post(URL, json={"texto": "voltou@empresa.com"})

    segunda = _campanha(db_session)
    pendente = _destinatario(db_session, segunda.id, "VOLTOU@empresa.com", "pendente")
    segunda.status = "pronta"
    db_session.commit()
    fake_email = FakeEmailProvider()

    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, FakeWhatsAppProvider())

    assert fake_email.envios == []
    db_session.refresh(pendente)
    assert pendente.status == "nao_enviado" and "devolvido" in pendente.motivo_falha


def test_campanha_com_whatsapp_junto_nao_manda_e_mail_ao_endereco_devolvido_mas_manda_o_whatsapp(client, onboarding_completo, db_session):
    primeira = _campanha(db_session)
    _destinatario(db_session, primeira.id, "voltou@empresa.com", "enviado")
    client.post(URL, json={"texto": "voltou@empresa.com"})

    mista = _campanha(db_session, canais=("email", "whatsapp"), template="prospeccao_inicial")
    _destinatario(db_session, mista.id, "voltou@empresa.com", "pendente", telefone="11999990000")
    mista.status = "pronta"
    db_session.commit()
    fake_email, fake_whatsapp = FakeEmailProvider(), FakeWhatsAppProvider()

    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert fake_email.envios == []  # o e-mail que voltou não é tentado de novo
    assert len(fake_whatsapp.envios) == 1  # o telefone da mesma pessoa continua valendo


def test_webmail_recusa_enviar_ao_endereco_registrado_como_inexistente(client, onboarding_completo, criar_conta_com_decisor, db_session, fake_email):
    conta, decisor = criar_conta_com_decisor(email="Inexistente@empresa.com")
    campanha = _campanha(db_session)
    _destinatario(db_session, campanha.id, "inexistente@empresa.com", "enviado")
    client.post(URL, json={"texto": "inexistente@empresa.com"})

    resposta = client.post("/api/v1/email-direto", json={"decisor_id": decisor.id, "assunto": "Oi", "corpo": "Olá"})

    assert resposta.status_code == 409
    assert "registrado como inexistente" in resposta.json()["detalhe"]
    assert fake_email.envios == []


def test_cadencia_cancela_a_mensagem_de_e_mail_para_endereco_registrado(
    client, onboarding_completo, criar_conta_com_decisor, fake_email, monkeypatch, db_session
):
    monkeypatch.setattr(cadencia_service, "datetime", _RelogioFixo)
    monkeypatch.setattr(envio_service, "datetime", _RelogioFixo)
    conta, decisor = criar_conta_com_decisor(email="cadencia@empresa.com")
    cadencia = client.post("/api/v1/cadencias", json={"nome": "C", "toques": _TOQUES}).json()
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    for item in client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json():
        client.post(f"/api/v1/aprovacoes/{item['aprovacao_id']}/aprovar")
    client.post(f"/api/v1/cadencias/{cadencia['id']}/ativar")
    campanha = _campanha(db_session)
    _destinatario(db_session, campanha.id, "cadencia@empresa.com", "enviado")
    client.post(URL, json={"texto": "cadencia@empresa.com"})

    resultado = client.post("/api/v1/envios/processar").json()

    assert resultado["enviadas"] == 0 and fake_email.envios == []
    assert resultado["bloqueadas_email_inexistente"] == 1


def test_endereco_que_nao_existe_no_sistema_nao_e_bloqueado_e_a_resposta_explica_o_motivo(client, onboarding_completo, db_session):
    corpo = client.post(URL, json={"texto": "mailer-daemon@googlemail.com"}).json()

    assert corpo["registrados"] == [] and corpo["nao_encontrados"] == ["mailer-daemon@googlemail.com"]
    assert "nada foi bloqueado" in corpo["motivo_nao_encontrados"]
    assert client.get("/api/v1/bloqueios-contato").json() == []


def test_liberar_o_bloqueio_desfaz_a_marca_manual_e_volta_a_poder_enviar(
    client, onboarding_completo, criar_conta_com_decisor, db_session, fake_email
):
    conta, decisor = criar_conta_com_decisor(email="engano@empresa.com")
    campanha = _campanha(db_session)
    destinatario = _destinatario(db_session, campanha.id, "engano@empresa.com", "enviado")
    client.post(URL, json={"texto": "engano@empresa.com"})
    bloqueio = client.get("/api/v1/bloqueios-contato").json()[0]

    assert client.delete(f"/api/v1/bloqueios-contato/{bloqueio['id']}").status_code == 204

    db_session.refresh(destinatario)
    assert destinatario.bounce_em is None
    assert client.post("/api/v1/email-direto", json={"decisor_id": decisor.id, "assunto": "Oi", "corpo": "Olá"}).status_code == 200


def test_bloqueio_de_um_tenant_nao_vale_para_outro(client, onboarding_completo, criar_conta_com_decisor, db_session, fake_email):
    campanha = _campanha(db_session)
    _destinatario(db_session, campanha.id, "mesmo@empresa.com", "enviado")
    client.post(URL, json={"texto": "mesmo@empresa.com"})
    from app.services import bloqueio_contato_service

    assert bloqueio_contato_service.emails_inviaveis(db_session, "outro-tenant") == set()
    assert "mesmo@empresa.com" in bloqueio_contato_service.emails_inviaveis(db_session, TENANT_ID)
