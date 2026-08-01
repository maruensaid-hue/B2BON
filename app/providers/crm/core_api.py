from app.providers.crm.base import CrmProvider

_MENSAGEM_NAO_IMPLEMENTADO = (
    "Integração com o núcleo B2B ON ainda não implementada. Use StubCrmProvider em desenvolvimento e testes."
)


class CoreApiCrmProvider(CrmProvider):
    """Cliente do CRM do núcleo B2B ON.

    Assinatura mantida estável para que o PREDATOR já dependa da porta
    `CrmProvider`, não desta implementação. O corpo é implementado quando o
    núcleo expuser a API de oportunidades — até lá, todo ambiente usa
    `StubCrmProvider`.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def criar_ou_atualizar_oportunidade(self, tenant_id: str, conta_id: int, dados: dict) -> str:
        raise NotImplementedError(_MENSAGEM_NAO_IMPLEMENTADO)

    def anexar_nota(self, tenant_id: str, oportunidade_id: str, texto: str) -> None:
        raise NotImplementedError(_MENSAGEM_NAO_IMPLEMENTADO)
