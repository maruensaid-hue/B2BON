from app.providers.email_validation.base import EmailVerificationProvider, ResultadoVerificacao

_MENSAGEM_NAO_IMPLEMENTADO = (
    "Integração com verificador de e-mail externo ainda não implementada. "
    "Use StubEmailVerificationProvider em desenvolvimento e testes."
)


class ExternalEmailVerificationProvider(EmailVerificationProvider):
    """Cliente de um verificador de e-mail externo (ex.: ZeroBounce,
    Kickbox).

    Assinatura mantida estável para que o PREDATOR já dependa da porta
    `EmailVerificationProvider`, não desta implementação. O corpo é
    implementado quando uma integração real for contratada — até lá, todo
    ambiente usa `StubEmailVerificationProvider`.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def verificar(self, email: str) -> ResultadoVerificacao:
        raise NotImplementedError(_MENSAGEM_NAO_IMPLEMENTADO)
