from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModoAgenteSchema(BaseModel):
    modo: str


class DefinirModoRequestSchema(BaseModel):
    modo: str


class TestarAgenteRequestSchema(BaseModel):
    pergunta: str


class TestarAgenteResponseSchema(BaseModel):
    resposta: str
    evidencias: list[dict]


class PerguntarAgenteRequestSchema(BaseModel):
    tenant_id_alvo: str
    pergunta: str


class PerguntaAgenteSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id_alvo: str
    tenant_id_alvo_nome: str = ""
    tenant_id_perguntante: str
    tenant_id_perguntante_nome: str = ""
    pergunta: str
    resposta_rascunho: str | None
    resposta_final: str | None
    evidencias: list[dict]
    status: str
    criado_em: datetime
    respondido_em: datetime | None


class AprovarPerguntaRequestSchema(BaseModel):
    resposta_final: str | None = None


class RecusarPerguntaRequestSchema(BaseModel):
    motivo: str | None = None
