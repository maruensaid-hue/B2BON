from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepresentanteSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    cpf: str | None
    chave_pix: str
    percentual_comissao: float
    ativo: bool
    criado_em: datetime


class RepresentanteSelfServiceSchema(BaseModel):
    """Listagem pública pro checkout — nunca expõe CPF/PIX."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str


class CriarRepresentanteRequestSchema(BaseModel):
    nome: str
    email: str
    cpf: str | None = None
    chave_pix: str
    percentual_comissao: float


class AtualizarRepresentanteRequestSchema(BaseModel):
    nome: str
    email: str
    cpf: str | None = None
    chave_pix: str
    percentual_comissao: float
    ativo: bool
