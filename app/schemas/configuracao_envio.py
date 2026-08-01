from datetime import datetime, time

from pydantic import BaseModel, ConfigDict


class ConfiguracaoEnvioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    remetente_nome: str
    remetente_email: str
    assinatura: str
    horario_inicio: time
    horario_fim: time
    criado_em: datetime
    atualizado_em: datetime


class ConfiguracaoEnvioUpsertSchema(BaseModel):
    remetente_nome: str
    remetente_email: str
    assinatura: str = ""
    horario_inicio: time
    horario_fim: time
