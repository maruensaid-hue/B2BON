from pydantic import BaseModel


class RampaStatusSchema(BaseModel):
    canal: str
    dias_de_uso: int
    limite_diario: int
    usado_hoje: int
    restante_hoje: int
