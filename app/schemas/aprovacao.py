from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AprovacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    mensagem_id: int
    status: str
    aprovador_id: str | None
    criado_em: datetime
    decidido_em: datetime | None


class AprovacaoFilaItemSchema(BaseModel):
    aprovacao_id: int
    status: str
    mensagem_id: int
    canal: str
    template_id: str | None
    conteudo: str
    cadencia_id: int
    conta_id: int
    decisor_id: int
    criado_em: datetime


class EditarMensagemRequestSchema(BaseModel):
    conteudo: str


class RejeitarRequestSchema(BaseModel):
    motivo: str | None = None


class AprovarLoteRequestSchema(BaseModel):
    ids: list[int]
