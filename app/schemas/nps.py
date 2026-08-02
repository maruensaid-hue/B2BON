from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfiguracaoNpsSchema(BaseModel):
    dias_apos_reuniao_realizada: int


class ConfiguracaoNpsUpsertSchema(BaseModel):
    dias_apos_reuniao_realizada: int


class PesquisaNpsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    decisor_id: int
    marco: str
    nota: int | None
    classificacao: str | None
    enviada_em: datetime
    respondida_em: datetime | None
    criado_em: datetime


class ResponderNpsRequestSchema(BaseModel):
    nota: int


class DistribuicaoNpsSchema(BaseModel):
    promotor: int
    neutro: int
    detrator: int
