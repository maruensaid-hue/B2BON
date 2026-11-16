"""Recusa por spam/bloqueio de reputação (pedido do PO em 16/11/2026): separada do e-mail inexistente, conta numa taxa própria que aparece no Relatório de
Entrega e, acima de 2% dos envios dos últimos 7 dias, pausa o canal de e-mail do tenant (salvo tenant isento) até a taxa cair."""
from datetime import UTC, datetime

import pytest

from app.models.bloqueio_contato import BloqueioContato
from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.pausa_canal import PausaCanal
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import bloqueio_contato_service, reputacao_service
from app.services.errors import RegraNegocioViolada
from app.services.relatorio_entrega_service import classificar_devolucao

TENANT_ID = "tenant-teste"

AVISO_INEXISTENTE = (
    "Address not found\nYour message wasn't delivered to {email} because the address couldn't be found.\n"
    "The response from the remote server was: 550 5.1.1 The email account that you tried to reach does not exist."
)
AVISO_SPAM = (
    "Message blocked\nYour message to {email} has been blocked. See technical details below for more information.\n"
    "The response from the remote server was: 550 5.7.1 Our system has detected that this message is likely unsolicited mail."
)


def _campanha_com_envios(db_session, quantidade: int) -> Campanha:
    campanha = Campanha(tenant_id=TENANT_ID, nome="Fim de ano", tipo="marketing", canais=["email"])
    db_session.add(campanha)
    db_session.flush()
    agora = datetime.now(UTC).replace(tzinfo=None)
    for numero in range(quantidade):
        db_session.add(
            CampanhaDestinatario(
                tenant_id=TENANT_ID, campanha_id=campanha.id, nome=f"Pessoa {numero}", email=f"p{numero}@cliente.com", status="enviado", enviado_em=agora
            )
        )
    db_session.commit()
    return campanha


def _garantir_tenant(db_session, isento: bool = False) -> Tenant:
    tenant = db_session.query(Tenant).filter_by(id=TENANT_ID).one_or_none()
    if tenant is None:
        tenant = Tenant(id=TENANT_ID, razao_social="Empresa teste")
        db_session.add(tenant)
    tenant.isento_pausa_spam = isento
    db_session.commit()
    return tenant


def _registrar(client, texto: str, tipo: str = "auto") -> dict:
    resposta = client.post("/api/v1/relatorio-entrega/bounces-manuais", json={"texto": texto, "tipo": tipo})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (AVISO_INEXISTENTE.format(email="a@b.com"), "inexistente"),
        (AVISO_SPAM.format(email="a@b.com"), "spam"),
        ("Mensagem bloqueada: a@b.com recusou por política de reputação", "spam"),
        ("a@b.com", "inexistente"),  # só o endereço, sem aviso: o comportamento de antes
    ],
)
def test_aviso_colado_diz_se_e_endereco_inexistente_ou_recusa_por_spam(texto, esperado):
    assert classificar_devolucao(texto, "a@b.com") == esperado


def test_aviso_com_os_dois_casos_classifica_cada_endereco_pelo_proprio_trecho():
    texto = AVISO_INEXISTENTE.format(email="sumiu@x.com") + "\n" + "-" * 800 + "\n" + AVISO_SPAM.format(email="barrou@y.com")

    assert classificar_devolucao(texto, "sumiu@x.com") == "inexistente"
    assert classificar_devolucao(texto, "barrou@y.com") == "spam"


def test_recusa_por_spam_aparece_no_relatorio_separada_do_inexistente(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 200)

    corpo = _registrar(client, AVISO_SPAM.format(email="p1@cliente.com") + "\n" + "-" * 800 + "\n" + AVISO_INEXISTENTE.format(email="p2@cliente.com"))

    assert sorted(corpo["registrados"]) == ["p1@cliente.com", "p2@cliente.com"]
    assert corpo["recusados_spam"] == ["p1@cliente.com"]
    origens = {b.email: b.origem for b in db_session.query(BloqueioContato).filter_by(tenant_id=TENANT_ID)}
    assert origens == {"p1@cliente.com": "email_recusado_spam", "p2@cliente.com": "email_inexistente"}
    # os dois deixam de receber e-mail em toda a plataforma
    assert {"p1@cliente.com", "p2@cliente.com"} <= bloqueio_contato_service.emails_inviaveis(db_session, TENANT_ID)

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["recusas_spam"] == 1
    assert saude["enviados_recusas"] == 200
    assert saude["taxa_recusa_spam"] == pytest.approx(0.005)
    assert saude["nivel_recusa_spam"] == "ok"
    assert saude["pausado"] is False


def test_entre_1_e_2_por_cento_so_avisa(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 100)

    _registrar(client, "p1@cliente.com", tipo="spam")

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["nivel_recusa_spam"] == "alerta"
    assert saude["pausado"] is False and saude["pausado_por_spam"] is False


def test_abaixo_da_amostra_minima_nao_pausa(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 10)

    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["taxa_recusa_spam"] == pytest.approx(0.2)
    assert saude["nivel_recusa_spam"] == "alerta"
    assert saude["pausado"] is False


def test_acima_de_2_por_cento_pausa_o_canal_e_trava_campanha_nova(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 60)

    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")  # 2/60 = 3,3%

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["nivel_recusa_spam"] == "critico"
    assert saude["pausado"] is True and saude["pausado_por_spam"] is True
    with pytest.raises(RegraNegocioViolada, match="recusaram como spam"):
        reputacao_service.exigir_canal_nao_pausado(db_session, TENANT_ID, "email")
    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email")  # envios agendados aguardam


def test_canal_reabre_sozinho_quando_a_taxa_cai(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 60)
    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")
    assert client.get("/api/v1/relatorio-entrega").json()["saude_email"]["pausado_por_spam"] is True

    _campanha_com_envios(db_session, 100)  # mais e-mails saíram sem recusa: 2/160 = 1,25%

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["pausado"] is False and saude["nivel_recusa_spam"] == "alerta"
    reputacao_service.exigir_canal_nao_pausado(db_session, TENANT_ID, "email")  # não levanta


def test_liberar_recusa_registrada_por_engano_tira_da_taxa(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 60)
    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")

    for bloqueio in db_session.query(BloqueioContato).filter_by(tenant_id=TENANT_ID).all():
        assert client.delete(f"/api/v1/bloqueios-contato/{bloqueio.id}").status_code in (200, 204)

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["recusas_spam"] == 0 and saude["pausado"] is False
    assert not {"p1@cliente.com", "p2@cliente.com"} & bloqueio_contato_service.emails_inviaveis(db_session, TENANT_ID)


def test_cliente_nao_desfaz_a_pausa_por_spam_so_o_super_admin(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 60)
    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")
    assert client.get("/api/v1/relatorio-entrega").json()["saude_email"]["pausado_por_spam"] is True

    usuario = db_session.query(Usuario).filter_by(email="teste@tenant-teste.com.br").one()
    usuario.papel = "admin"
    db_session.commit()
    assert client.post("/api/v1/canais/email/reativar").status_code == 409

    usuario.papel = "super_admin"
    db_session.commit()
    assert client.post("/api/v1/canais/email/reativar").json()["pausado"] is False
    # as recusas de antes da revisão não pausam de novo
    assert client.get("/api/v1/relatorio-entrega").json()["saude_email"]["pausado"] is False


def test_tenant_isento_ve_as_recusas_mas_nao_pausa(client, onboarding_completo, db_session):
    _garantir_tenant(db_session, isento=True)
    _campanha_com_envios(db_session, 60)

    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")

    saude = client.get("/api/v1/relatorio-entrega").json()["saude_email"]
    assert saude["recusas_spam"] == 2 and saude["nivel_recusa_spam"] == "critico"
    assert saude["isento_pausa_spam"] is True
    assert saude["pausado"] is False
    reputacao_service.exigir_canal_nao_pausado(db_session, TENANT_ID, "email")  # não levanta


def test_super_admin_isenta_o_tenant_e_a_pausa_por_spam_sai_na_hora(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    _campanha_com_envios(db_session, 60)
    _registrar(client, "p1@cliente.com\np2@cliente.com", tipo="spam")
    assert db_session.query(PausaCanal).filter_by(tenant_id=TENANT_ID, canal="email", ativa=True).count() == 1

    resposta = client.put(f"/api/v1/admin/tenants/{TENANT_ID}/isencao-pausa-spam", json={"isento": True})

    assert resposta.status_code == 200 and resposta.json()["isento_pausa_spam"] is True
    db_session.expire_all()
    assert reputacao_service.canal_pausado(db_session, TENANT_ID, "email") is False


def test_admin_comum_nao_muda_a_isencao(client, onboarding_completo, db_session):
    _garantir_tenant(db_session)
    usuario = db_session.query(Usuario).filter_by(email="teste@tenant-teste.com.br").one()
    usuario.papel = "admin"
    db_session.commit()

    resposta = client.put(f"/api/v1/admin/tenants/{TENANT_ID}/isencao-pausa-spam", json={"isento": True})

    assert resposta.status_code == 403
    db_session.expire_all()
    assert db_session.query(Tenant).filter_by(id=TENANT_ID).one().isento_pausa_spam is False


def test_bloqueio_do_envio_por_api_conta_como_recusa_por_spam_e_nao_como_bounce(db_session):
    _garantir_tenant(db_session)

    saude = reputacao_service.registrar_evento(db_session, TENANT_ID, "email", "recusa_spam", 3)

    assert saude["bounces"] == 0
    assert reputacao_service.saude_recusas_spam(db_session, TENANT_ID)["recusas_spam"] == 3
