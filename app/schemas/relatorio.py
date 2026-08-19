from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MetricasRelatorioSchema(BaseModel):
    periodo_inicio: datetime
    periodo_fim: datetime
    tenants_ativos_distribuidor: int
    tenants_ativos_revendedor: int
    tenants_ativos_cliente: int
    novas_ativacoes: int
    licencas_suspensas_periodo: int
    licencas_suspensas_total: int
    franquia_limite_total: int
    franquia_usado_total: int
    receita_periodo: float
    churn_atual: int


class DashboardRelatorioSchema(BaseModel):
    atual: MetricasRelatorioSchema
    anterior: MetricasRelatorioSchema


class ConfiguracaoRelatorioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    cadencia: str
    ultimo_envio_em: datetime | None
    criado_em: datetime


class DefinirConfiguracaoRelatorioRequestSchema(BaseModel):
    cadencia: str
