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


class AdicionarDestinatariosDeDecisoresRequestSchema(BaseModel):
    decisor_ids: list[int]


class DestinatarioAvulsoSchema(BaseModel):
    nome: str
    email: str | None = None
    telefone: str | None = None


class AdicionarDestinatariosAvulsosRequestSchema(BaseModel):
    destinatarios: list[DestinatarioAvulsoSchema]
