from pydantic import BaseModel


class RegistrarEventoReputacaoRequestSchema(BaseModel):
    tenant_id: str
    canal: str
    tipo_evento: str  # enviado | bounce | spam_report
    quantidade: int = 1


class SaudeCanalSchema(BaseModel):
    canal: str
    enviados: int
    bounces: int
    spam_reports: int
    taxa_bounce: float
    taxa_spam: float
    pausado: bool
    limiar_bounce: float
    limiar_spam: float
