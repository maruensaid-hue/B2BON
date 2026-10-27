import smtplib
import time
from email.message import EmailMessage

from app.core.config import settings
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio, montar_html_com_pixel


_TENTATIVAS = 3
_ESPERA_ENTRE_TENTATIVAS = 2.0  # segundos, multiplicado pelo número da tentativa


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
        mensagem_id: int | None = None,
        campanha_destinatario_id: int | None = None,
        reply_to: str | None = None,
    ) -> ResultadoEnvio:
        mensagem = EmailMessage()
        mensagem["Subject"] = assunto
        mensagem["From"] = f"{remetente_nome} <{remetente_email}>"
        mensagem["To"] = destinatario
        if reply_to:
            mensagem["Reply-To"] = reply_to
        mensagem.set_content(corpo)

        if pixel_url:
            # multipart/alternative: texto puro continua a parte principal
            # (clientes que preferem texto simples ignoram o HTML) — o
            # pixel só existe pra quem renderiza a parte HTML.
            mensagem.add_alternative(montar_html_com_pixel(corpo, pixel_url), subtype="html")

        ultimo: ResultadoEnvio | None = None
        for tentativa in range(1, _TENTATIVAS + 1):
            ultimo = self._enviar_uma_vez(mensagem)
            if ultimo.sucesso or not ultimo.transitoria:
                return ultimo
            if tentativa < _TENTATIVAS:
                time.sleep(_ESPERA_ENTRE_TENTATIVAS * tentativa)  # a rede costuma voltar em segundos (reinício do serviço, oscilação)
        return ultimo

    def _enviar_uma_vez(self, mensagem: EmailMessage) -> ResultadoEnvio:
        # A etapa e o endereço IP entram no motivo da falha: "Connection unexpectedly closed" sozinho não diz se caiu ao conectar, na criptografia, no
        # login ou no envio — e foi o que separou a rede bloqueada (plano gratuito do Render) de um servidor que aceita e depois derruba a conexão.
        etapa = "conectar"
        ip = ""
        try:
            with smtplib.SMTP(self.host, self.porta, timeout=15) as servidor:
                ip = self._ip_conectado(servidor)
                if self.usar_tls:
                    etapa = "negociar a criptografia (TLS)"
                    servidor.starttls()
                if self.usuario:
                    etapa = "autenticar"
                    servidor.login(self.usuario, self.senha)
                etapa = "enviar a mensagem"
                servidor.send_message(mensagem)
            return ResultadoEnvio(sucesso=True)
        except smtplib.SMTPRecipientsRefused as erro:
            # O servidor recusou o endereço de destino (RCPT TO). 5xx = endereço inválido ou inexistente: falha só desse destinatário, o envio segue com os
            # outros; 4xx = recusa temporária. Atenção: esta classe herda de OSError, então precisa vir antes da captura de rede abaixo — do contrário um
            # endereço inválido era tratado como queda de rede e a campanha ficava repetindo o mesmo destinatário sem avançar.
            codigos = [codigo for codigo, _ in erro.recipients.values()]
            detalhe = "; ".join(
                f"{endereco}: {codigo} {' '.join(texto.decode(errors='replace').split())}"
                for endereco, (codigo, texto) in erro.recipients.items()
            )
            return ResultadoEnvio(
                sucesso=False,
                motivo_falha=self._motivo(etapa, ip, f"destinatário recusado pelo servidor ({detalhe})"),
                transitoria=bool(codigos) and all(400 <= codigo < 500 for codigo in codigos),
            )
        except smtplib.SMTPResponseException as erro:
            # 4xx é recusa temporária do servidor (caixa cheia, limite de envio, greylisting); 5xx é definitiva (credencial, remetente, destinatário).
            return ResultadoEnvio(sucesso=False, motivo_falha=self._motivo(etapa, ip, erro), transitoria=400 <= erro.smtp_code < 500)
        except smtplib.SMTPServerDisconnected as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=self._motivo(etapa, ip, erro), transitoria=True)
        except smtplib.SMTPException as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=self._motivo(etapa, ip, erro))
        except OSError as erro:  # rede (SMTPException já foi tratada acima: ela também é OSError)
            return ResultadoEnvio(sucesso=False, motivo_falha=self._motivo(etapa, ip, erro), transitoria=True)

    @staticmethod
    def _ip_conectado(servidor: smtplib.SMTP) -> str:
        try:
            return str(servidor.sock.getpeername()[0])
        except (AttributeError, OSError):
            return ""

    def _motivo(self, etapa: str, ip: str, erro: Exception | str) -> str:
        onde = f"{self.host}:{self.porta}" + (f" (IP {ip})" if ip else "")
        return f"Falha ao {etapa} em {onde}: {erro}"
