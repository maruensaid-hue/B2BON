from app.providers.rede_social.base import RedeSocialProvider

_MENSAGEM_NAO_IMPLEMENTADO = (
    "Integração com a Rede Social B2B do núcleo ainda não implementada. "
    "Use StubRedeSocialProvider em desenvolvimento e testes."
)


class CoreApiRedeSocialProvider(RedeSocialProvider):
    """Cliente da Rede Social B2B do núcleo.

    Assinatura mantida estável para que o PREDATOR já dependa da porta
    `RedeSocialProvider`, não desta implementação. O corpo é implementado
    quando o núcleo expuser a API de assinantes — até lá, todo ambiente usa
    `StubRedeSocialProvider`.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def eh_assinante(self, identificador: str) -> bool:
        raise NotImplementedError(_MENSAGEM_NAO_IMPLEMENTADO)
