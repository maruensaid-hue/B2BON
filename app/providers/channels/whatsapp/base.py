from abc import ABC, abstractmethod

from pydantic import BaseModel


class ResultadoEnvio(BaseModel):
    sucesso: bool
    id_externo: str | None = None
    motivo_falha: str | None = None


class TemplateInfo(BaseModel):
    nome: str
    status: str  # aprovado | pendente | rejeitado
    corpo: str


class WhatsAppProvider(ABC):
    """Porta de envio via WhatsApp Business API oficial (Meta).

    Único caminho de envio de WhatsApp permitido no PREDATOR — nenhuma
    história do E3 pode enviar por fora desta porta (E3-H2).
    """

    @abstractmethod
    def enviar_template(self, telefone: str, template_id: str, variaveis: dict) -> ResultadoEnvio:
        raise NotImplementedError

    @abstractmethod
    def enviar_texto_livre(self, telefone: str, texto: str) -> ResultadoEnvio:
        raise NotImplementedError

    @abstractmethod
    def listar_templates(self) -> list[TemplateInfo]:
        raise NotImplementedError
