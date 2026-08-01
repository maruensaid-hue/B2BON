from app.providers.channels.email.base import EmailProvider, ResultadoEnvio


class StubEmailProvider(EmailProvider):
    """Registra o envio em memória, sem SMTP real — dev/teste."""

    def __init__(self) -> None:
        self.envios: list[dict] = []

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
    ) -> ResultadoEnvio:
        self.envios.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "corpo": corpo,
                "remetente_nome": remetente_nome,
                "remetente_email": remetente_email,
            }
        )
        return ResultadoEnvio(sucesso=True, id_externo=f"stub-{len(self.envios)}")
