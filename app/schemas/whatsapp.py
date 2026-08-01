from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplateWhatsAppSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    nome: str
    corpo: str
    status: str
    sincronizado_em: datetime


class WebhookWhatsAppRequestSchema(BaseModel):
    # tenant_id explícito: webhooks vêm da infraestrutura da Meta, sem
    # X-Tenant-Id — em produção seria resolvido via phone_number_id.
    tenant_id: str
    telefone: str
    texto: str


class WebhookEmailRequestSchema(BaseModel):
    # idem — resolvido via inbound-parse do ESP em produção.
    tenant_id: str
    email: str
    texto: str
