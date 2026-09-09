from pydantic import BaseModel


class ResultadoBuscaSchema(BaseModel):
    tipo: str  # conta | negocio | proposta | cadencia | tenant
    id: int | str
    titulo: str
    subtitulo: str | None = None
    rota: str
