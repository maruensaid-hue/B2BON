from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CampanhaDestinatarioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campanha_id: int
    decisor_id: int | None
    nome: str
    email: str | None
    telefone: str | None
    empresa: str | None = None
    status: str
    enviado_em: datetime | None
    motivo_falha: str | None
    criado_em: datetime


class CampanhaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    nome: str
    tipo: str
    canais: list[str]
    assunto: str | None
    conteudo_email: str | None
    template_whatsapp_id: str | None
    status: str
    criado_em: datetime
    atualizado_em: datetime


class CampanhaDetalheSchema(CampanhaSchema):
    destinatarios: list[CampanhaDestinatarioSchema]
    metricas: dict[str, int]


class CampanhaPreviaSchema(BaseModel):
    """E-mail da campanha já personalizado para um destinatário (sem o rodapé de descadastro)."""
    destinatario_nome: str | None
    assunto: str
    corpo: str


class CampanhaCreateSchema(BaseModel):
    nome: str
    tipo: str  # vendas | marketing
    canais: list[str]
    assunto: str | None = None
    conteudo_email: str | None = None
    template_whatsapp_id: str | None = None


class CampanhaUpdateSchema(BaseModel):
    nome: str
    tipo: str
    canais: list[str]
    assunto: str | None = None
    conteudo_email: str | None = None
    template_whatsapp_id: str | None = None


class EditarDestinatarioRequestSchema(BaseModel):
    """Dados para corrigir um destinatário; `reenviar` e `atualizar_contato_crm` controlam o efeito de trocar o e-mail."""
    nome: str
    email: str | None = None
    telefone: str | None = None
    empresa: str | None = None
    # Trocar o e-mail de quem já recebeu a campanha só vale com isto marcado: o novo endereço volta para a fila de envio.
    reenviar: bool = False
    # Para destinatário vindo do CRM: grava o novo e-mail também no cadastro do contato.
    atualizar_contato_crm: bool = False


class NaoQuerReceberRequestSchema(BaseModel):
    """Motivo opcional do bloqueio (padrão: "Informado manualmente: não quer receber.")."""
    motivo: str | None = None


class MarcarProntaRequestSchema(BaseModel):
    """Lista opcional de destinatários para enviar só a eles; os demais pendentes ficam para o próximo envio."""
    # Nulo = todos os pendentes; lista = só estes (os demais pendentes aguardam o próximo envio).
    destinatario_ids: list[int] | None = None


class AdicionarDestinatariosDeDecisoresRequestSchema(BaseModel):
    decisor_ids: list[int]


class DestinatarioAvulsoSchema(BaseModel):
    """Uma pessoa da lista colada na campanha (sem cadastro no CRM). A `empresa` é opcional e alimenta o marcador `[Empresa]` do e-mail."""

    nome: str
    email: str | None = None
    telefone: str | None = None
    empresa: str | None = None


class AdicionarDestinatariosAvulsosRequestSchema(BaseModel):
    destinatarios: list[DestinatarioAvulsoSchema]
