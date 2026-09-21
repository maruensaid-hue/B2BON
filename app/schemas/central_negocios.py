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
    # DEBUG TEMPORÁRIO — ver nota em `central_negocios_client.Mercado`.
    debug_erro_cambio: str | None = None


class NoticiaSchema(BaseModel):
    portal: str
    titulo: str
    link: str
    publicado_em: str | None
