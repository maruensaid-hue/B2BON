import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio, montar_html_com_pixel


class SmtpEmailProvider(EmailProvider):
    """Implementação real via SMTP (`smtplib`, biblioteca padrão)."""

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
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as servidor:
                servidor.starttls()
                if settings.smtp_user:
                    servidor.login(settings.smtp_user, settings.smtp_password)
                servidor.send_message(mensagem)
            return ResultadoEnvio(sucesso=True)
        except (smtplib.SMTPException, OSError) as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=str(erro))
