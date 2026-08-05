from pydantic import BaseModel


class MetricaNorteSchema(BaseModel):
    mes_atual: str
    valor_mes_atual: int
    meta: int | None
    valor_mes_anterior: int
    variacao_percentual: float | None


class ConfiguracaoPainelSchema(BaseModel):
    meta_mensal_reunioes: int | None


class ConfiguracaoPainelUpsertSchema(BaseModel):
    meta_mensal_reunioes: int | None


class IndicadoresEnergiaSchema(BaseModel):
    taxa_resposta_por_canal: dict[str, float]
    taxa_abertura_email: float | None
    taxa_qualificacao: float
    tempo_medio_ate_primeira_reuniao_horas: float | None
    origem_oportunidade: dict[str, int]


class IndicadoresAtritoSchema(BaseModel):
    taxa_no_show: float | None
    tempo_medio_parado_entre_estagios_horas: float | None


class IndicadoresResponseSchema(BaseModel):
    periodo_inicio: str
    periodo_fim: str
    energia: IndicadoresEnergiaSchema
    atrito: IndicadoresAtritoSchema


class RankingAssinanteSchema(BaseModel):
    """Só campos agregados — nenhum dado de conta/decisor/mensagem do
    assinante (isolamento multi-tenant do E8-H3, verificado por teste)."""

    tenant_id: str
    valor_mes_atual: int
    meta: int | None
    atingimento: float | None
    alerta_baixo_uso: bool
