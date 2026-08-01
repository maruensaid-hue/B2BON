from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RegistroTratamentoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_tratamento: str
    finalidade: str
    base_legal: str
    dados_tratados: list
    balanceamento_documentado: str
    versao: int
    ativo: bool
    criado_em: datetime


class RegistroTratamentoCreateSchema(BaseModel):
    tipo_tratamento: str
    finalidade: str
    dados_tratados: list[str]
    balanceamento_documentado: str


class MinimizacaoResponseSchema(BaseModel):
    conforme: bool
    divergencias: list[str]


class RegistroTratamentoTenantSchema(BaseModel):
    tenant_id: str
    icp_ids: list[int]
    fontes_dados: list[str]
    canais_ativos: list[str]
    dados_tratados: list[str]
    base_legal: str
