from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndicacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    promotor_decisor_id: int
    promotor_conta_id: int
    codigo_indicacao: str
    canal: str
    indicado_nome: str | None
    indicado_identificador: str | None
    intra_rede: bool
    conta_gerada_id: int | None
    status: str
    criado_em: datetime
    convertida_em: datetime | None


class ConverterIndicacaoRequestSchema(BaseModel):
    conta_id: int
