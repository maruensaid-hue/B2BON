import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio


class SmtpEmailProvider(EmailProvider):
    """Implementação real via SMTP (`smtplib`, biblioteca padrão)."""

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
    ) -> ResultadoEnvio:
        mensagem = EmailMessage()
        mensagem["Subject"] = assunto
        mensagem["From"] = f"{remetente_nome} <{remetente_email}>"
        mensagem["To"] = destinatario
        mensagem.set_content(corpo)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as servidor:
                servidor.starttls()
                if settings.smtp_user:
                    servidor.login(settings.smtp_user, settings.smtp_password)
                servidor.send_message(mensagem)
            return ResultadoEnvio(sucesso=True)
        except (smtplib.SMTPException, OSError) as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=str(erro))
