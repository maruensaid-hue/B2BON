from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OfertaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    icp_id: int | None
    nome: str
    descricao: str
    diferenciais: list
    provas_sociais: list
    faixa_preco_min: float | None
    faixa_preco_max: float | None
    ativo: bool
    criado_em: datetime


class OfertaCreateSchema(BaseModel):
    icp_id: int | None = None
    nome: str
    descricao: str
    diferenciais: list[str] = []
    provas_sociais: list[str] = []
    faixa_preco_min: float | None = None
    faixa_preco_max: float | None = None


class MaterialOfertaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    oferta_id: int
    nome_arquivo: str
    tipo_mime: str
    tamanho_bytes: int
    criado_em: datetime
