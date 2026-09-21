from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FaqItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    pergunta: str
    resposta: str
    criado_em: datetime


class FaqItemCreateSchema(BaseModel):
    pergunta: str
    resposta: str


class TurnoFaqSchema(BaseModel):
    autor: Literal["usuario", "ia"]
    texto: str


class FaqPerguntarRequestSchema(BaseModel):
    pergunta: str
    # Painel de IA docado (raio-X 2026-09-21): o backend continua sem
    # persistir conversa (mesma cautela de custo já documentada em
    # faq_service.responder) — o frontend reenvia os últimos turnos
    # visíveis a cada pergunta pra dar continuidade de contexto dentro
    # da mesma sessão de painel aberto, sem precisar de tabela nova.
    historico: list[TurnoFaqSchema] | None = None


class FaqPerguntarResponseSchema(BaseModel):
    resposta: str
