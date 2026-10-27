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

    resultado = provider.enviar(
        "dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@predator.com", "tenant-teste"
    )

    assert resultado.sucesso is True
    mensagem = _mensagem_enviada(mock_smtp)
    assert mensagem.is_multipart() is False
    assert mensagem.get_content().strip() == "Corpo do e-mail"


@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_com_pixel_envia_multipart_com_imagem_embutida(mock_smtp: MagicMock):
    provider = SmtpEmailProvider()
    pixel_url = "https://b2bon-api.onrender.com/api/v1/webhooks/email/aberto/abc123.png"

    provider.enviar(
        "dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@predator.com", "tenant-teste", pixel_url
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
def test_credenciais_explicitas_por_tenant_sao_usadas_no_lugar_da_conta_global(mock_smtp: MagicMock):
    """Raio-X 2026-08-27: por-tenant precisa mandar pela conta SMTP do
    próprio tenant, não pela conta global da plataforma — sem isso,
    "configurar sua própria conta" não fazia diferença nenhuma no envio
    de verdade."""
    provider = SmtpEmailProvider(
        host="smtp.tenant.com.br", porta=465, usuario="tenant@empresa.com.br", senha="senha-do-tenant",
        usar_tls=False,
    )

    resultado = provider.enviar(
        "dest@empresa.com", "Assunto", "Corpo do e-mail", "Vendas", "vendas@tenant.com.br", "tenant-x"
    )

    assert resultado.sucesso is True
    mock_smtp.assert_called_once_with("smtp.tenant.com.br", 465, timeout=15)
    servidor = mock_smtp.return_value.__enter__.return_value
    servidor.starttls.assert_not_called()
    servidor.login.assert_called_once_with("tenant@empresa.com.br", "senha-do-tenant")


@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_pixel_url_com_caractere_html_e_escapado(mock_smtp: MagicMock):
    provider = SmtpEmailProvider()

    provider.enviar(
        "dest@empresa.com",
        "Assunto",
        "Corpo com <tag> e & comercial",
        "Vendas",
        "vendas@predator.com",
        "tenant-teste",
        pixel_url="https://x.com/a?b=1&c=2",
    )

    mensagem = _mensagem_enviada(mock_smtp)
    html = mensagem.get_body(preferencelist=("html",)).get_content()
    assert "<tag>" not in html
    assert "&lt;tag&gt;" in html
    assert "a?b=1&amp;c=2" in html


def _enviar(provider):
    return provider.enviar("dest@empresa.com", "Assunto", "Corpo", "Vendas", "vendas@predator.com", "tenant-teste")


@patch("app.providers.channels.email.smtp.time.sleep")
@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_rede_fora_do_ar_tenta_tres_vezes_e_marca_a_falha_como_transitoria(mock_smtp: MagicMock, mock_sleep: MagicMock):
    mock_smtp.side_effect = OSError(101, "Network is unreachable")

    resultado = _enviar(SmtpEmailProvider())

    assert resultado.sucesso is False and resultado.transitoria is True
    assert "Network is unreachable" in resultado.motivo_falha
    assert mock_smtp.call_count == 3 and mock_sleep.call_count == 2


@patch("app.providers.channels.email.smtp.time.sleep")
@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_rede_que_volta_na_segunda_tentativa_envia_normalmente(mock_smtp: MagicMock, mock_sleep: MagicMock):
    servidor = MagicMock()
    mock_smtp.side_effect = [OSError(101, "Network is unreachable"), MagicMock(__enter__=MagicMock(return_value=servidor))]

    resultado = _enviar(SmtpEmailProvider())

    assert resultado.sucesso is True and mock_smtp.call_count == 2
    servidor.send_message.assert_called_once()


@patch("app.providers.channels.email.smtp.time.sleep")
@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_recusa_definitiva_do_servidor_nao_e_repetida(mock_smtp: MagicMock, mock_sleep: MagicMock):
    import smtplib

    mock_smtp.side_effect = smtplib.SMTPResponseException(550, b"mailbox unavailable")

    resultado = _enviar(SmtpEmailProvider())

    assert resultado.sucesso is False and resultado.transitoria is False
    assert mock_smtp.call_count == 1 and mock_sleep.call_count == 0


@patch("app.providers.channels.email.smtp.time.sleep")
@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_recusa_temporaria_4xx_do_servidor_e_transitoria(mock_smtp: MagicMock, mock_sleep: MagicMock):
    import smtplib

    mock_smtp.side_effect = smtplib.SMTPResponseException(451, b"try again later")

    assert _enviar(SmtpEmailProvider()).transitoria is True


@patch("app.providers.channels.email.smtp.time.sleep")
@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_falha_diz_em_que_etapa_e_em_que_endereco_a_conexao_caiu(mock_smtp: MagicMock, mock_sleep: MagicMock):
    import smtplib

    servidor = MagicMock()
    servidor.sock.getpeername.return_value = ("142.250.0.1", 587)
    servidor.starttls.side_effect = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    mock_smtp.return_value.__enter__.return_value = servidor

    resultado = _enviar(SmtpEmailProvider(host="smtp.gmail.com", porta=587, usuario="u", senha="s"))

    assert resultado.sucesso is False and resultado.transitoria is True
    assert resultado.motivo_falha == (
        "Falha ao negociar a criptografia (TLS) em smtp.gmail.com:587 (IP 142.250.0.1): Connection unexpectedly closed"
    )


@patch("app.providers.channels.email.smtp.smtplib.SMTP")
def test_recusa_de_credencial_diz_que_falhou_ao_autenticar(mock_smtp: MagicMock):
    import smtplib

    servidor = MagicMock()
    servidor.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    mock_smtp.return_value.__enter__.return_value = servidor

    resultado = _enviar(SmtpEmailProvider(host="smtp.gmail.com", porta=587, usuario="u", senha="s"))

    assert resultado.transitoria is False and resultado.motivo_falha.startswith("Falha ao autenticar em smtp.gmail.com:587")
