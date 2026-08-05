from abc import ABC, abstractmethod

from app.llm.schemas import LLMRequest, LLMResponse


class LLMIndisponivel(Exception):
    """Erro genérico, independente de fornecedor, para falhas na chamada à
    IA (autenticação, rede, limite de taxa) — a camada de serviço decide
    como isso vira uma resposta ao usuário; o provider não conhece
    RegraNegocioViolada (evita acoplar a porta de LLM ao domínio)."""


class LLMProvider(ABC):
    """Interface que qualquer provedor de LLM deve implementar.

    Isola o motor PREDATOR de um fornecedor específico (mitigação de risco
    de dependência — Seção 14 da especificação).
    """

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
