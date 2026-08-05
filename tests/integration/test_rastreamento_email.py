from fastapi.testclient import TestClient

from app.main import app
from app.models.mensagem import Mensagem
from app.services import rastreamento_service

TENANT_ID = "tenant-teste"


def test_pixel_registra_abertura_e_devolve_imagem(client, db_session, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    mensagem = Mensagem(
        tenant_id=TENANT_ID, decisor_id=decisor.id, canal="email", conteudo="Ola", status="enviado"
    )
    db_session.add(mensagem)
    db_session.commit()
    token = rastreamento_service.gerar_token_abertura(TENANT_ID, mensagem.id)

    resposta = client.get(f"/api/v1/webhooks/email/aberto/{token}.png")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.content == rastreamento_service.PIXEL_PNG_1X1

    db_session.refresh(mensagem)
    assert mensagem.aberto_em is not None


def test_pixel_com_token_invalido_ainda_devolve_imagem(client):
    """Nunca falha a imagem por token ruim — só não registra nada (Onda I)."""
    resposta = client.get("/api/v1/webhooks/email/aberto/token-forjado.png")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "image/png"


def test_pixel_nao_exige_autenticacao(client):
    """Endpoint público de verdade — cliente sem nenhum header de auth
    (E-mail do destinatário nunca teria um token JWT)."""
    cliente_sem_header = TestClient(app)

    resposta = cliente_sem_header.get("/api/v1/webhooks/email/aberto/qualquer-coisa.png")

    assert resposta.status_code == 200
