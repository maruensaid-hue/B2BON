from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ResultadoVerificacao:
    valido: bool
    motivo: str | None = None


class EmailVerificationProvider(ABC):
    """Porta para verificação prévia de e-mail (existência do endereço),
    para reduzir bounces (E10-H3) — fronteira de integração externa, mesmo
    espírito de `WhatsAppProvider`/`EmailProvider` (Onda 2)."""

    @abstractmethod
    def verificar(self, email: str) -> ResultadoVerificacao:
        raise NotImplementedError
