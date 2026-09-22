from pydantic import BaseModel


class CotacaoMoedaSchema(BaseModel):
    codigo: str
    nome: str
    valor: float
    variacao_pct: float


class PontoSerieSchema(BaseModel):
    data: str
    valor: float


class IndiceSchema(BaseModel):
    nome: str
    pontos: float
    variacao_pct: float
    serie: list[PontoSerieSchema]


class MercadoSchema(BaseModel):
    indices: list[IndiceSchema]
    cambio: list[CotacaoMoedaSchema]


class NoticiaSchema(BaseModel):
    portal: str
    titulo: str
    link: str
    publicado_em: str | None
