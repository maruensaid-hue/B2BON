from pydantic import BaseModel


class ResultadoBuscaSchema(BaseModel):
    tipo: str  # conta | negocio | proposta | decisor | cadencia | tenant
    id: int | str
    titulo: str
    subtitulo: str | None = None
    rota: str
