from unittest.mock import MagicMock, patch

from app.providers.channels.email.smtp import SmtpEmailProvider


def _mensagem_enviada(mock_smtp) -> object:
    """`send_message` é chamado dentro do `with smtplib.SMTP(...) as servidor`
    — o objeto EmailMessage passado pra ele é o que queremos inspecionar."""
    servidor = mock_smtp.return_value.__enter__.return_value
    return servidor.send_message.call_args[0][0]


@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_sem_pixel_envia_so_texto_puro(mock_smtp: MagicMock):
    provider = SmtpEmailProvider()

    resultado = provider.enviar("dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@predator.com")

    assert resultado.sucesso is True
    mensagem = _mensagem_enviada(mock_smtp)
    assert mensagem.is_multipart() is False
    assert mensagem.get_content().strip() == "Corpo do e-mail"


@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_com_pixel_envia_multipart_com_imagem_embutida(mock_smtp: MagicMock):
    provider = SmtpEmailProvider()
    pixel_url = "https://b2bon-api.onrender.com/api/v1/webhooks/email/aberto/abc123.png"

    provider.enviar(
        "dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@predator.com", pixel_url=pixel_url
    )

    mensagem = _mensagem_enviada(mock_smtp)
    assert mensagem.is_multipart() is True

    parte_html = mensagem.get_body(preferencelist=("html",))
    assert parte_html is not None
    html = parte_html.get_content()
    assert pixel_url in html
    assert 'width="1" height="1"' in html

    parte_texto = mensagem.get_body(preferencelist=("plain",))
    assert parte_texto.get_content().strip() == "Corpo do e-mail"


@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_pixel_url_com_caractere_html_e_escapado(mock_smtp: MagicMock):
    provider = SmtpEmailProvider()

    provider.enviar(
        "dest@empresa.com",
        "Assunto",
        "Corpo com <tag> e & comercial",
        "Vendas",
        "vendas@predator.com",
        pixel_url="https://x.com/a?b=1&c=2",
    )

    mensagem = _mensagem_enviada(mock_smtp)
    html = mensagem.get_body(preferencelist=("html",)).get_content()
    assert "<tag>" not in html
    assert "&lt;tag&gt;" in html
    assert "a?b=1&amp;c=2" in html
