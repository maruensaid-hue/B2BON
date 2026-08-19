import httpx
import pytest

from app.core.config import settings
from app.providers.channels.email.sendgrid import SendGridEmailProvider


class _RespostaFalsa:
    def __init__(self, status_code: int = 202, message_id: str = "msg-1", texto: str = "") -> None:
        self.status_code = status_code
        self.headers = {"X-Message-Id": message_id} if message_id else {}
        self.text = texto


@pytest.fixture(autouse=True)
def _config_sendgrid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sendgrid_api_key", "SG.chave-de-teste")
    monkeypatch.setattr(settings, "sendgrid_remetente_email", "contato@mail.cyberfort.com.br")


def test_sucesso_retorna_id_externo_do_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(202, "msg-abc"))

    resultado = SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@empresa.com", "tenant-teste"
    )

    assert resultado.sucesso is True
    assert resultado.id_externo == "msg-abc"


def test_erro_http_retorna_falha_com_motivo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _RespostaFalsa(401, texto="Unauthorized"))

    resultado = SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo", "Vendas", "vendas@empresa.com", "tenant-teste"
    )

    assert resultado.sucesso is False
    assert "401" in resultado.motivo_falha
    assert "Unauthorized" in resultado.motivo_falha


def test_erro_de_rede_retorna_falha_sem_levantar(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post_falho(*args, **kwargs):
        raise httpx.ConnectError("conexão recusada")

    monkeypatch.setattr(httpx, "post", _post_falho)

    resultado = SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo", "Vendas", "vendas@empresa.com", "tenant-teste"
    )

    assert resultado.sucesso is False
    assert "conexão recusada" in resultado.motivo_falha


def test_payload_usa_from_da_plataforma_e_reply_to_do_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem domínio autenticado por tenant, o envelope From tem que ser
    sempre o domínio da plataforma — o e-mail configurado pelo tenant
    (ConfiguracaoEnvio.remetente_email) vira Reply-To, não o From."""
    capturado = {}

    def _post_falso(url, json, headers, timeout):
        capturado.update(json=json, headers=headers)
        return _RespostaFalsa()

    monkeypatch.setattr(httpx, "post", _post_falso)

    SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo", "Vendas da Empresa X", "vendedor@empresax.com.br", "tenant-abc"
    )

    corpo = capturado["json"]
    assert corpo["from"] == {"email": "contato@mail.cyberfort.com.br", "name": "Vendas da Empresa X"}
    assert corpo["reply_to"] == {"email": "vendedor@empresax.com.br"}
    assert capturado["headers"]["Authorization"] == "Bearer SG.chave-de-teste"


def test_custom_args_leva_tenant_id_pro_webhook_de_reputacao(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado = {}
    monkeypatch.setattr(httpx, "post", lambda url, json, headers, timeout: capturado.update(json=json) or _RespostaFalsa())

    SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo", "Vendas", "vendas@empresa.com", "tenant-xyz"
    )

    assert capturado["json"]["personalizations"][0]["custom_args"] == {"tenant_id": "tenant-xyz"}
    assert capturado["json"]["personalizations"][0]["to"] == [{"email": "dest@empresa.com"}]


def test_sem_pixel_manda_so_texto_puro(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado = {}
    monkeypatch.setattr(httpx, "post", lambda url, json, headers, timeout: capturado.update(json=json) or _RespostaFalsa())

    SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@empresa.com", "tenant-teste"
    )

    assert capturado["json"]["content"] == [{"type": "text/plain", "value": "Corpo do e-mail"}]


def test_com_pixel_inclui_parte_html_com_imagem_embutida(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado = {}
    monkeypatch.setattr(httpx, "post", lambda url, json, headers, timeout: capturado.update(json=json) or _RespostaFalsa())
    pixel_url = "https://b2bon-api.onrender.com/api/v1/webhooks/email/aberto/abc123.png"

    SendGridEmailProvider().enviar(
        "dest@empresa.com", "Assunto", "Corpo", "Vendas", "vendas@empresa.com", "tenant-teste", pixel_url
    )

    conteudo = capturado["json"]["content"]
    assert conteudo[0] == {"type": "text/plain", "value": "Corpo"}
    assert conteudo[1]["type"] == "text/html"
    assert pixel_url in conteudo[1]["value"]
    assert 'width="1" height="1"' in conteudo[1]["value"]
