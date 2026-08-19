from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EstagioFunilSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    nome: str
    ordem: int
    tipo: str


class DefinirEstagioRequestSchema(BaseModel):
    nome: str | None = None
    ordem: int | None = None
    tipo: str | None = None


class NegocioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    conta_nome: str = ""
    decisor_id: int | None = None
    decisor_nome: str | None = None
    vendedor_usuario_id: int | None
    estagio_id: int
    nome: str
    valor: float
    probabilidade: int
    origem: str
    ganho_em: datetime | None
    perdido_em: datetime | None
    motivo_perda: str | None
    criado_em: datetime
    atualizado_em: datetime


class CriarNegocioRequestSchema(BaseModel):
    conta_id: int
    decisor_id: int | None = None
    nome: str
    valor: float = 0.0
    probabilidade: int = 50
    vendedor_usuario_id: int | None = None
    estagio_id: int | None = None


class AtualizarNegocioRequestSchema(BaseModel):
    nome: str
    valor: float = 0.0
    probabilidade: int = 50
    decisor_id: int | None = None


class MoverEstagioRequestSchema(BaseModel):
    estagio_id: int
    motivo_perda: str | None = None


class AtividadeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int | None
    negocio_id: int | None
    usuario_id: int | None
    tipo: str
    descricao: str
    criado_em: datetime


class RegistrarAtividadeRequestSchema(BaseModel):
    tipo: str
    descricao: str


class PropostaNegocioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    negocio_id: int
    versao: int
    nome_arquivo: str
    tipo_mime: str
    tamanho_bytes: int
    gerada_automaticamente: bool
    enviada_por_usuario_id: int | None
    criado_em: datetime


class CancelarClienteRequestSchema(BaseModel):
    motivo: str | None = None


class DefinirCustoAquisicaoRequestSchema(BaseModel):
    periodo: str
    valor: float


class CustoAquisicaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    periodo: str
    valor: float


class EstagioFunilResumoSchema(BaseModel):
    estagio_id: int
    nome: str
    tipo: str
    quantidade: int
    valor_total: float


class DashboardFunilSchema(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    estagios: list[EstagioFunilResumoSchema]
    taxa_conversao: float | None


class AtividadePorUsuarioSchema(BaseModel):
    usuario_id: int
    nome: str
    quantidade: int


class DashboardAtividadeSchema(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    por_vendedor: list[AtividadePorUsuarioSchema]
    total_equipe: int


class DashboardEconomiaSchema(BaseModel):
    periodo: str
    ltv_medio: float | None
    cac: float | None
    taxa_churn: float | None
    novos_clientes: int
    clientes_ativos_inicio_periodo: int
    clientes_cancelados_periodo: int
    roi: float | None
    cs_score: float | None
    nps_medio: float | None


class DashboardFlywheelSchema(BaseModel):
    metrica_norte: dict
    indicadores_energia: dict
    indicadores_atrito: dict
    funil: DashboardFunilSchema
