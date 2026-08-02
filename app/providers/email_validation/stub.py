import re

from app.providers.email_validation.base import EmailVerificationProvider, ResultadoVerificacao

_PADRAO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StubEmailVerificationProvider(EmailVerificationProvider):
    """Checagem de sintaxe + lista de domínios inválidos conhecidos —
    dev/teste enquanto não há um verificador externo real contratado."""

    def __init__(self) -> None:
        self.dominios_invalidos: set[str] = set()

    def verificar(self, email: str | None) -> ResultadoVerificacao:
        if not email or not _PADRAO_EMAIL.match(email):
            return ResultadoVerificacao(valido=False, motivo="sintaxe de e-mail inválida")

        dominio = email.rsplit("@", 1)[-1].lower()
        if dominio in self.dominios_invalidos:
            return ResultadoVerificacao(valido=False, motivo=f"domínio inválido/inexistente: {dominio}")

        return ResultadoVerificacao(valido=True)
