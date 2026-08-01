from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MensagemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    cadencia_id: int
    decisor_id: int
    canal: str
    template_id: str | None
    conteudo: str
    variante_ab: str | None
    status: str
    agendado_para: datetime | None
    enviado_em: datetime | None
    criado_em: datetime
