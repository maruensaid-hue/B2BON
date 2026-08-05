from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReuniaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    decisor_id: int
    vendedor_id: str
    data_hora: datetime
    status: str
    origem_crm_id: str | None
    horarios_propostos: list
    horario_confirmado: datetime | None
    link_reuniao: str | None
    origem_calendario_id: str | None
    reagendado_de_id: int | None
    lembrete_d1_enviado_em: datetime | None
    lembrete_h2_enviado_em: datetime | None
    qualificada_confirmada: bool | None
    motivo_qualificacao: str | None
    criado_em: datetime


class ReuniaoListaItemSchema(BaseModel):
    id: int
    tenant_id: str
    conta_id: int
    conta_nome: str
    decisor_id: int
    decisor_nome: str
    vendedor_id: str
    data_hora: datetime
    status: str
    horarios_propostos: list
    horario_confirmado: datetime | None
    link_reuniao: str | None
    qualificada_confirmada: bool | None
    criado_em: datetime


class ProporHorariosRequestSchema(BaseModel):
    vendedor_id: str
    duracao_minutos: int = 30


class ConfirmarReuniaoRequestSchema(BaseModel):
    horario_escolhido: datetime


class ReagendarReuniaoRequestSchema(BaseModel):
    novo_horario: datetime


class MarcarResultadoReuniaoRequestSchema(BaseModel):
    status: str  # realizada | no_show


class ConfirmarQualificacaoRequestSchema(BaseModel):
    qualificada: bool
    motivo: str | None = None


class ProcessarLembretesResponseSchema(BaseModel):
    lembretes_d1_enviados: int
    lembretes_h2_enviados: int
