from pydantic import BaseModel


class OnboardingStatusSchema(BaseModel):
    icp_ativo: bool
    oferta_cadastrada: bool
    comunicacao_configurada: bool
    pronto_para_prospeccao: bool
    orientacao: list[str]
