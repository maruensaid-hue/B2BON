from app.providers.channels.email.base import EmailProvider, ResultadoEnvio


class EmailDesativadoProvider(EmailProvider):
    """No-op honesto pra produção sem `SMTP_HOST` configurado — diferente
    do `StubEmailProvider` (dev/teste), que sempre reporta sucesso mesmo
    sem enviar nada de verdade. Usar o stub em produção fazia o convite
    de empresa (Rede Social) parecer enviado quando na real nada saía,
    sem nenhum aviso pro usuário (raio-X de produção real)."""

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
        return ResultadoEnvio(sucesso=False, motivo_falha="Envio de e-mail não está configurado no servidor.")
