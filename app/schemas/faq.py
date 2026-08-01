from datetime import datetime

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
