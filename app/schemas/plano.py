from pydantic import BaseModel, ConfigDict


class PlanoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    franquia_contas_mes: int
    max_usuarios: int
    preco_mensal: float
