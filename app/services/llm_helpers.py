from app.llm.base import LLMIndisponivel, LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse
from app.services.errors import RegraNegocioViolada


def gerar(llm: LLMProvider, request: LLMRequest) -> LLMResponse:
    """Chama o LLM traduzindo falha de infraestrutura (chave ausente, rede,
    limite de taxa) em erro de negócio claro — sem isto, qualquer problema
    na chamada à IA virava um 500 genérico sem explicação para quem usa a
    tela (bug real: geração de cadência "não funcionava" sem nenhuma pista
    do porquê)."""
    try:
        return llm.generate(request)
    except LLMIndisponivel as erro:
        raise RegraNegocioViolada(
            f"Não foi possível gerar o texto com IA no momento ({erro}). "
            "Tente novamente em instantes; se persistir, avise o administrador."
        ) from erro
