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
        pixel_url: str | None = None,
    ) -> ResultadoEnvio:
        """`pixel_url`, quando presente, é o rastreio de abertura (Onda I) —
        exige mandar uma parte HTML do e-mail (texto puro não carrega
        imagem), então implementações reais devem enviar multipart/
        alternative com o pixel de 1x1 embutido na parte HTML."""
        raise NotImplementedError
