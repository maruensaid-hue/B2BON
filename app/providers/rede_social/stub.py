from app.providers.rede_social.base import RedeSocialProvider


class StubRedeSocialProvider(RedeSocialProvider):
    """Conjunto de identificadores (e-mail/telefone) considerados
    assinantes da Rede Social B2B — controlável em dev/teste enquanto o
    núcleo não está disponível para integração."""

    def __init__(self) -> None:
        self.assinantes: set[str] = set()

    def eh_assinante(self, identificador: str) -> bool:
        return identificador in self.assinantes
