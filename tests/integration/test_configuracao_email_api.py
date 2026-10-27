from app.models.campanha import Campanha, CampanhaDestinatario
from app.models.configuracao_email_api import ConfiguracaoEmailApi
from app.services import rastreamento_service

TENANT_ID = "tenant-teste"
URL = "/api/v1/configuracao-email-api"


def test_sem_configuracao_a_consulta_volta_vazia(client):
    resposta = client.get(URL)

    assert resposta.status_code == 200 and resposta.json() is None


def test_primeira_configuracao_exige_chave_e_email_valido(client):
    sem_chave = client.put(URL, json={"remetente_email": "vendas@cliente.com"})
    email_ruim = client.put(URL, json={"chave_api": "SG.chave-do-cliente", "remetente_email": "isso-nao-e-email"})

    assert sem_chave.status_code == 422 and email_ruim.status_code == 422


def test_salvar_nao_devolve_a_chave_e_editar_sem_chave_mantem_a_salva(client, db_session):
    salvo = client.put(
        URL, json={"chave_api": "SG.chave-secreta-1234", "remetente_email": "vendas@cliente.com", "remetente_nome": "Maria | Cliente", "chave_webhook": "chave-publica"}
    )

    assert salvo.status_code == 200
    corpo = salvo.json()
    assert corpo["chave_mascarada"] == "••••1234" and "chave_api" not in corpo and "secreta" not in salvo.text
    assert corpo["tem_chave_webhook"] is True
    assert corpo["url_webhook"].endswith("/webhooks/envio/eventos")  # sem o nome do fornecedor

    editado = client.put(URL, json={"remetente_email": "novo@cliente.com", "remetente_nome": "Novo nome"})

    assert editado.status_code == 200 and editado.json()["remetente_email"] == "novo@cliente.com"
    db_session.expire_all()
    config = db_session.query(ConfiguracaoEmailApi).filter_by(tenant_id=TENANT_ID).one()
    assert config.chave_api == "SG.chave-secreta-1234" and config.chave_webhook == "chave-publica"  # mantidas


def test_teste_de_envio_usa_o_envio_salvo_e_manda_para_o_proprio_usuario(client, fake_email):
    assert client.post(f"{URL}/testar").status_code == 422  # nada salvo ainda

    client.put(URL, json={"chave_api": "SG.chave-secreta-1234", "remetente_email": "vendas@cliente.com"})
    resposta = client.post(f"{URL}/testar")

    assert resposta.status_code == 200 and resposta.json()["sucesso"] is True
    assert fake_email.envios[-1]["destinatario"] == "teste@tenant-teste.com.br"


def test_remover_volta_ao_estado_sem_envio_por_api(client):
    client.put(URL, json={"chave_api": "SG.chave-secreta-1234", "remetente_email": "vendas@cliente.com"})

    removida = client.delete(URL)

    assert removida.status_code == 200 and removida.json() == {"removida": True}
    assert client.get(URL).json() is None
    assert client.delete(URL).json() == {"removida": False}


def test_endpoint_do_pixel_de_campanha_registra_a_abertura(client, db_session):
    campanha = Campanha(tenant_id=TENANT_ID, nome="Com pixel", tipo="marketing", canais=["email"])
    db_session.add(campanha)
    db_session.flush()
    destinatario = CampanhaDestinatario(tenant_id=TENANT_ID, campanha_id=campanha.id, nome="A", email="a@teste.com", status="enviado", pixel_incluido=True)
    db_session.add(destinatario)
    db_session.commit()
    token = rastreamento_service.gerar_token_abertura(TENANT_ID, destinatario.id, campanha=True)

    resposta = client.get(f"/api/v1/webhooks/email/aberto/{token}.png")

    assert resposta.status_code == 200 and resposta.headers["content-type"] == "image/png"
    db_session.expire_all()
    assert db_session.get(CampanhaDestinatario, destinatario.id).aberto_em is not None
