from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int | None
    icp_id: int | None
    oferta_id: int | None
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
    ab_teste_habilitado: bool = False


class ToqueCadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cadencia_id: int
    ordem: int
    canal: str
    intervalo_dias_apos_anterior: int
    template_whatsapp_id: str | None
    ab_teste_habilitado: bool


class DefinirTemplateWhatsAppRequestSchema(BaseModel):
    template_whatsapp_id: str


class CadenciaCreateSchema(BaseModel):
    nome: str
    toques: list[ToqueCadenciaCreateSchema]
    tipo: str = "prospeccao"
    # Opcional — só relevante pra quem tem mais de um ICP ativo ao mesmo
    # tempo (comparação de campanhas, `icp_service.performance`). Sem
    # informar, cai no ICP ativo (o primeiro encontrado, mesmo
    # comportamento de antes desta correção).
    icp_id: int | None = None


class GerarCadenciaRequestSchema(BaseModel):
    conta_ids: list[int]


class GerarCadenciaResponseSchema(BaseModel):
    contas_processadas: list[int]
    contas_sem_decisor: list[int]
    mensagens_geradas: int
    toques_bloqueados_restricao: int = 0
    toques_falha_ia: int = 0


class AtivarCadenciaResponseSchema(BaseModel):
    cadencia: CadenciaSchema
    franquia: dict


class VarianteAbSchema(BaseModel):
    total: int
    respondentes: int
    taxa_resposta: float


class RelatorioAbTesteSchema(BaseModel):
    variante_a: VarianteAbSchema
    variante_b: VarianteAbSchema
    z_score: float
    significativo: bool
    vencedora: str | None
