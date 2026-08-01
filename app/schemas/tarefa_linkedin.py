from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TarefaLinkedinSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    mensagem_id: int
    decisor_id: int
    texto: str
    link_perfil: str | None
    status: str
    criado_em: datetime
    atualizado_em: datetime


class MarcarTarefaLinkedinRequestSchema(BaseModel):
    executada: bool
