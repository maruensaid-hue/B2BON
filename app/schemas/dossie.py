from pydantic import BaseModel


class DossieSchema(BaseModel):
    decisor_nome: str
    conta_nome: str
    dores: list[str]
    respostas: list[dict]
    score_total: float | None
    score_criterios: dict
    proxima_acao_recomendada: str
    oportunidade_crm_id: str | None = None
