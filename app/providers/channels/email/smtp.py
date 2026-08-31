import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio, montar_html_com_pixel


class SmtpEmailProvider(EmailProvider):
    """Implementação real via SMTP (`smtplib`, biblioteca padrão).

    Sem argumento nenhum, usa a conta SMTP global (`settings.smtp_*`) —
    só existe pros e-mails de sistema/plataforma (onboarding, convite,
    relatório periódico), que continuam saindo pela conta da CyberFort.
    Com credenciais explícitas (raio-X 2026-08-27, `resolver_email_
    provider`), passa a mandar pela conta SMTP própria do tenant — sem
    isso, disparo de cadência/campanha em nome do tenant continuava
    saindo pela infraestrutura compartilhada da plataforma."""

    def __init__(
        self,
        host: str | None = None,
        porta: int | None = None,
        usuario: str | None = None,
        senha: str | None = None,
        usar_tls: bool | None = None,
    ) -> None:
        self.host = host if host is not None else settings.smtp_host
        self.porta = porta if porta is not None else settings.smtp_port
        self.usuario = usuario if usuario is not None else settings.smtp_user
        self.senha = senha if senha is not None else settings.smtp_password
        self.usar_tls = usar_tls if usar_tls is not None else True

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
        tenant_id: str,
        pixel_url: str | None = None,
    ) -> ResultadoEnvio:
        mensagem = EmailMessage()
        mensagem["Subject"] = assunto
        mensagem["From"] = f"{remetente_nome} <{remetente_email}>"
        mensagem["To"] = destinatario
        mensagem.set_content(corpo)

        if pixel_url:
            # multipart/alternative: texto puro continua a parte principal
            # (clientes que preferem texto simples ignoram o HTML) — o
            # pixel só existe pra quem renderiza a parte HTML.
            mensagem.add_alternative(montar_html_com_pixel(corpo, pixel_url), subtype="html")

        try:
            with smtplib.SMTP(self.host, self.porta, timeout=15) as servidor:
                if self.usar_tls:
                    servidor.starttls()
                if self.usuario:
                    servidor.login(self.usuario, self.senha)
                servidor.send_message(mensagem)
            return ResultadoEnvio(sucesso=True)
        except (smtplib.SMTPException, OSError) as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=str(erro))
