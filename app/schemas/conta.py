from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    icp_id: int
    cnpj: str | None
    nome: str
    dominio: str | None
    porte: str | None
    segmento: str | None
    regiao: str | None
    score_aderencia: float | None
    status: str
    motivo_descarte: str | None
    origem: str | None
    neo4j_node_id: str | None
    criado_em: datetime
    atualizado_em: datetime


class GerarListaRequestSchema(BaseModel):
    quantidade: int


class FranquiaSchema(BaseModel):
    limite: int
    usado: int
    restante: int


class GerarListaResponseSchema(BaseModel):
    contas: list[ContaSchema]


class CampoEnriquecidoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campo: str
    valor: str
    fonte: str
    coletado_em: datetime


class EnriquecerContaResponseSchema(BaseModel):
    campos: list[CampoEnriquecidoSchema]


class GrafoNoSchema(BaseModel):
    id: str
    tipo: str
    propriedades: dict


class GrafoArestaSchema(BaseModel):
    origem: str
    destino: str
    tipo: str


class GrafoContaResponseSchema(BaseModel):
    nos: list[GrafoNoSchema]
    arestas: list[GrafoArestaSchema]
