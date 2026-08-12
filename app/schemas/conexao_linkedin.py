from datetime import datetime

from pydantic import BaseModel


class ImportarConexoesLinkedinRequestSchema(BaseModel):
    conteudo_csv: str


class ImportarConexoesLinkedinResponseSchema(BaseModel):
    total_importado: int


class StatusConexoesLinkedinSchema(BaseModel):
    total: int
    atualizado_em: datetime | None
