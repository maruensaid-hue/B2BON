from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MensagemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    cadencia_id: int | None
    decisor_id: int
    toque_cadencia_id: int | None
    canal: str
    template_id: str | None
    conteudo: str
    variante_ab: str | None
    status: str
    agendado_para: datetime | None
    enviado_em: datetime | None
    aberto_em: datetime | None
    motivo_falha: str | None
    tentativas_envio: int
    criado_em: datetime
