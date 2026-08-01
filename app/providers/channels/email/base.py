from abc import ABC, abstractmethod

from pydantic import BaseModel


class ResultadoEnvio(BaseModel):
    sucesso: bool
    id_externo: str | None = None
    motivo_falha: str | None = None


class EmailProvider(ABC):
    """Porta de envio de e-mail — isola o PREDATOR do provedor SMTP/ESP concreto."""

    @abstractmethod
    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
    ) -> ResultadoEnvio:
        raise NotImplementedError
