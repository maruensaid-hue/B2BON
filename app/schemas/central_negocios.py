from pydantic import BaseModel


class CotacaoMoedaSchema(BaseModel):
    codigo: str
    nome: str
    valor: float
    variacao_pct: float


class IbovespaSchema(BaseModel):
    pontos: float
    variacao_pct: float


class MercadoSchema(BaseModel):
    ibovespa: IbovespaSchema | None
    cambio: list[CotacaoMoedaSchema]


class NoticiaSchema(BaseModel):
    portal: str
    titulo: str
    link: str
    publicado_em: str | None
