import pytest

from app.models.conta import Conta
from app.models.decisor import Decisor

TENANT_ID = "tenant-teste"
TENANT_B = "tenant-b"


@pytest.fixture()
def conta_e_decisor(db_session):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", email="decisor@teste.com")
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


def test_enviar_com_sucesso(client, conta_e_decisor, fake_email):
    conta, decisor = conta_e_decisor

    resposta = client.post(
        "/api/v1/email-direto", json={"decisor_id": decisor.id, "assunto": "Assunto de teste", "corpo": "Olá!"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "enviado"
    assert corpo["conta_nome"] == conta.nome
    assert len(fake_email.envios) == 1


def test_enviar_decisor_de_outro_tenant_retorna_404(client, criar_usuario_autenticado, conta_e_decisor):
    _, decisor = conta_e_decisor
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")

    resposta = client.post(
        "/api/v1/email-direto",
        json={"decisor_id": decisor.id, "assunto": "Assunto", "corpo": "Corpo"},
        headers=headers_b,
    )

    assert resposta.status_code == 404


def test_listar_enviados_com_e_sem_filtro_de_conta(client, conta_e_decisor):
    conta, decisor = conta_e_decisor
    client.post("/api/v1/email-direto", json={"decisor_id": decisor.id, "assunto": "Assunto 1", "corpo": "Corpo 1"})

    resposta = client.get("/api/v1/email-direto")
    assert resposta.status_code == 200
    assert len(resposta.json()) == 1

    resposta_filtrada = client.get("/api/v1/email-direto", params={"conta_id": conta.id})
    assert len(resposta_filtrada.json()) == 1

    resposta_vazia = client.get("/api/v1/email-direto", params={"conta_id": conta.id + 999})
    assert resposta_vazia.json() == []


def test_listar_recebidos_com_e_sem_filtro_de_conta(client, db_session, conta_e_decisor):
    from app.services import email_direto_service

    conta, decisor = conta_e_decisor
    from tests.fakes import FakeEmailProvider

    email_direto_service.processar_recebido(
        db_session, TENANT_ID, decisor.id, "cliente@empresa.com", "Assunto", "Corpo", FakeEmailProvider()
    )

    resposta = client.get("/api/v1/email-direto/recebidos")
    assert resposta.status_code == 200
    assert len(resposta.json()) == 1
    assert resposta.json()[0]["remetente_email"] == "cliente@empresa.com"

    resposta_vazia = client.get("/api/v1/email-direto/recebidos", params={"conta_id": conta.id + 999})
    assert resposta_vazia.json() == []


def test_arquivar_conversa_e_pendentes(client, conta_e_decisor):
    conta, decisor = conta_e_decisor
    client.post("/api/v1/email-direto", json={"decisor_id": decisor.id, "assunto": "Assunto", "corpo": "Corpo"})

    pendentes = client.get("/api/v1/email-direto/pendentes-arquivamento").json()
    assert len(pendentes) == 1
    assert pendentes[0]["decisor_id"] == decisor.id
    assert pendentes[0]["total_enviados"] == 1

    resposta = client.post("/api/v1/email-direto/arquivar", json={"decisor_id": decisor.id})
    assert resposta.status_code == 200
    assert resposta.json() == {"enviados_arquivados": 1, "recebidos_arquivados": 0}

    assert client.get("/api/v1/email-direto/pendentes-arquivamento").json() == []
    assert client.get("/api/v1/email-direto").json() == []


def test_webhook_email_inbound_com_token_valido_persiste_e_retransmite(client, db_session, conta_e_decisor, fake_email):
    from app.services import resposta_service

    conta, decisor = conta_e_decisor
    token = resposta_service.gerar_token_resposta(TENANT_ID, decisor.id)

    resposta = client.post(
        "/api/v1/webhooks/email/inbound",
        data={
            "to": f"resp+{token}@respostas.teste.com.br",
            "from": "Cliente Teste <cliente@empresa.com>",
            "subject": "Re: Proposta",
            "text": "Aceito a proposta!",
        },
        headers={"Authorization": ""},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"recebido": True, "processado": True}

    recebidos = client.get("/api/v1/email-direto/recebidos").json()
    assert len(recebidos) == 1
    assert recebidos[0]["remetente_email"] == "cliente@empresa.com"
    assert recebidos[0]["assunto"] == "Re: Proposta"


def test_webhook_email_inbound_com_token_invalido_nao_derruba(client):
    resposta = client.post(
        "/api/v1/webhooks/email/inbound",
        data={"to": "resp+token-adulterado@respostas.teste.com.br", "from": "x@y.com", "subject": "x", "text": "x"},
        headers={"Authorization": ""},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"recebido": True, "processado": False}


def test_webhook_email_inbound_sem_token_no_destinatario_nao_derruba(client):
    resposta = client.post(
        "/api/v1/webhooks/email/inbound",
        data={"to": "contato@empresa.com", "from": "x@y.com", "subject": "x", "text": "x"},
        headers={"Authorization": ""},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"recebido": True, "processado": False}


def test_configuracao_get_e_put(client):
    resposta_inicial = client.get("/api/v1/email-direto/configuracao")
    assert resposta_inicial.status_code == 200
    assert resposta_inicial.json() == {"email_nome_exibicao": None, "email_assinatura": None}

    resposta_put = client.put(
        "/api/v1/email-direto/configuracao",
        json={"email_nome_exibicao": "Fulano de Tal", "email_assinatura": "Att, Fulano"},
    )

    assert resposta_put.status_code == 200
    assert resposta_put.json() == {"email_nome_exibicao": "Fulano de Tal", "email_assinatura": "Att, Fulano"}
