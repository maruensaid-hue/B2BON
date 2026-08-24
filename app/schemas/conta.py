from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    icp_id: int | None
    cnpj: str | None
    nome: str
    nome_fantasia: str | None
    dominio: str | None
    vendedor_usuario_id: int | None
    porte: str | None
    segmento: str | None
    regiao: str | None
    score_aderencia: float | None
    status: str
    motivo_descarte: str | None
    origem: str | None
    nps_classificacao: str | None
    nps_nota: int | None
    cliente_desde: datetime | None
    cliente_cancelado_em: datetime | None
    proximo_passo: str | None
    proximo_passo_em: datetime | None
    resumo_site: str | None
    observacoes: str | None
    neo4j_node_id: str | None
    criado_em: datetime
    atualizado_em: datetime


class GerarListaRequestSchema(BaseModel):
    quantidade: int


class DescartarContaRequestSchema(BaseModel):
    motivo: str


class AtualizarContaRequestSchema(BaseModel):
    nome: str
    cnpj: str | None = None
    nome_fantasia: str | None = None
    dominio: str | None = None
    segmento: str | None = None
    porte: str | None = None
    regiao: str | None = None
    resumo_site: str | None = None
    observacoes: str | None = None


class DefinirProximoPassoRequestSchema(BaseModel):
    proximo_passo: str | None = None
    proximo_passo_em: datetime | None = None


class CriarContaManualRequestSchema(BaseModel):
    nome: str
    cnpj: str | None = None
    dominio: str | None = None


class CriarLeadRequestSchema(BaseModel):
    nome: str
    cnpj: str | None = None
    dominio: str | None = None
    segmento: str | None = None
    porte: str | None = None
    regiao: str | None = None


class FranquiaSchema(BaseModel):
    limite: int
    usado: int
    restante: int


class GerarListaResponseSchema(BaseModel):
    contas: list[ContaSchema]


class ParticipanteEventoSchema(BaseModel):
    nome: str
    empresa: str
    cargo: str | None = None
    email: str | None = None
    telefone: str | None = None


class ImportarParticipantesRequestSchema(BaseModel):
    participantes: list[ParticipanteEventoSchema]


class ImportarParticipantesResponseSchema(BaseModel):
    contas_criadas: int
    contas_reaproveitadas: int
    decisores_criados: int
    contas: list[ContaSchema]
    # Só as contas novas entram na fila — as reaproveitadas presumivelmente
    # já passaram por enriquecimento antes.
    contas_enfileiradas_para_enriquecimento: int


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
