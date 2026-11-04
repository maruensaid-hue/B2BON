from abc import ABC, abstractmethod

from pydantic import BaseModel


class ResultadoEnvio(BaseModel):
    sucesso: bool
    id_externo: str | None = None
    motivo_falha: str | None = None
    # Código de erro devolvido pela Meta (ex.: 131047 = fora da janela de 24 h; 100 = parâmetro inválido / conta sem Direct Send).
    codigo_erro: int | None = None


class TemplateCriado(BaseModel):
    """Resposta da Meta ao criar um modelo: o id e o status inicial (em geral PENDING; utilidade às vezes já vem APPROVED)."""

    id_externo: str | None = None
    status: str | None = None
    erro: str | None = None


class InfoNumero(BaseModel):
    """O que a Meta diz do número conectado: serve para mostrar "conectado: +55 11 ..., nome X, qualidade verde" e testar a conexão."""

    numero_exibicao: str | None = None
    nome_verificado: str | None = None
    qualidade: str | None = None  # GREEN | YELLOW | RED | UNKNOWN
    erro: str | None = None


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
    def enviar_template(
        self, telefone: str, template_id: str, variaveis: dict, variavel_botao: str | None = None
    ) -> ResultadoEnvio:
        """`variavel_botao` (raio-X 2026-09-15): preenche a URL dinâmica de
        um botão de "Visitar site" do template (ex.: `https://wa.me/{{1}}`),
        pensado pra redirecionar o cliente pro WhatsApp pessoal do
        vendedor responsável pela conta assim que ele quiser responder —
        tira a conversa da API (sem regra de janela de 24h a partir daí).
        `None` quando não há vendedor com número cadastrado; o envio segue
        sem preencher o botão."""
        raise NotImplementedError

    @abstractmethod
    def enviar_texto_livre(self, telefone: str, texto: str) -> ResultadoEnvio:
        raise NotImplementedError

    @abstractmethod
    def enviar_direct_send(self, telefone: str, texto: str, categoria: str = "utility") -> ResultadoEnvio:
        """Direct Send da Meta (beta): mensagem iniciada pela empresa SEM template pré-aprovado, só nas categorias `utility` e
        `authentication` (marketing não existe aqui). A Meta revisa depois do envio; uso indevido leva a suspensão de 7 dias, bloqueio
        de 30 e perda definitiva do recurso. Quem chama decide se pode (ver `whatsapp_service`)."""
        raise NotImplementedError

    @abstractmethod
    def listar_templates(self) -> list[TemplateInfo]:
        raise NotImplementedError

    def info_numero(self) -> InfoNumero:
        return InfoNumero(erro="Conexão com a Meta não disponível neste ambiente.")

    def criar_template(self, nome: str, categoria: str, corpo: str, rodape: str | None = None) -> TemplateCriado:
        """Envia um modelo de mensagem para aprovação da Meta (whatsapp_business_management). Padrão: indisponível."""
        return TemplateCriado(erro="Criação de modelos não disponível neste ambiente.")
