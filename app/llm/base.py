from abc import ABC, abstractmethod

from app.llm.schemas import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Interface que qualquer provedor de LLM deve implementar.

    Isola o motor PREDATOR de um fornecedor específico (mitigação de risco
    de dependência — Seção 14 da especificação).
    """

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
