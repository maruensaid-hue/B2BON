from pydantic import BaseModel


class BuscaTitularResponseSchema(BaseModel):
    encontrado: bool
    decisor_id: int | None = None
    conta_id: int | None = None
    nome: str | None = None


class ExportacaoTitularResponseSchema(BaseModel):
    decisor: dict
    conta: dict
    turnos_conversa: list[dict]
    mensagens: list[dict]
    reunioes: list[dict]
    qualificacoes: list[dict]


class EliminarTitularResponseSchema(BaseModel):
    eliminado: bool
    identificador_hash: str
