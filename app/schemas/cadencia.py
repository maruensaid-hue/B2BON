from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int | None
    nome: str
    canais: list
    status: str
    tipo: str
    data_inicio: datetime | None
    criado_em: datetime


class ToqueCadenciaCreateSchema(BaseModel):
    ordem: int
    canal: str
    intervalo_dias_apos_anterior: int = 0
    template_whatsapp_id: str | None = None


class ToqueCadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cadencia_id: int
    ordem: int
    canal: str
    intervalo_dias_apos_anterior: int
    template_whatsapp_id: str | None


class CadenciaCreateSchema(BaseModel):
    nome: str
    toques: list[ToqueCadenciaCreateSchema]
    tipo: str = "prospeccao"


class GerarCadenciaRequestSchema(BaseModel):
    conta_ids: list[int]


class GerarCadenciaResponseSchema(BaseModel):
    contas_processadas: list[int]
    contas_sem_decisor: list[int]
    mensagens_geradas: int


class AtivarCadenciaResponseSchema(BaseModel):
    cadencia: CadenciaSchema
    franquia: dict
