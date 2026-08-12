from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DecisorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    nome: str
    cargo: str | None
    canal_provavel: str | None
    linkedin_url: str | None
    email: str | None
    telefone: str | None
    neo4j_node_id: str | None
    criado_em: datetime


class DecisorCreateSchema(BaseModel):
    nome: str
    cargo: str | None = None
    canal_provavel: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    telefone: str | None = None


class AtualizarDecisorRequestSchema(BaseModel):
    nome: str
    cargo: str | None = None
    email: str | None = None
    telefone: str | None = None
    linkedin_url: str | None = None
    # Nulo mantém a empresa atual — só reatribui quando vier preenchido
    # (E2-H2: contato cadastrado na empresa errada por engano, ou que
    # mudou de emprego, precisa poder ser movido sem recriar do zero).
    conta_id: int | None = None
