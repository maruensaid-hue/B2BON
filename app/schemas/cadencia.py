from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int | None
    icp_id: int | None
    oferta_id: int | None
    lista_prospeccao_id: int | None = None
    nome: str
    canais: list
    status: str
    tipo: str
    data_inicio: datetime | None
    cancelar_ao_responder: bool
    pausar_empresa_ao_responder: bool = False
    prospeccao_automatica: bool = False
    direct_send_aceito_por: str | None = None
    direct_send_aceito_em: datetime | None = None
    criado_em: datetime


class ToqueCadenciaCreateSchema(BaseModel):
    ordem: int
    canal: str
    intervalo_dias_apos_anterior: int = 0
    template_whatsapp_id: str | None = None
    ab_teste_habilitado: bool = False
    whatsapp_sem_template: bool = False


class ToqueCadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cadencia_id: int
    ordem: int
    canal: str
    intervalo_dias_apos_anterior: int
    template_whatsapp_id: str | None
    ab_teste_habilitado: bool
    whatsapp_sem_template: bool = False


class DefinirWhatsAppSemTemplateRequestSchema(BaseModel):
    whatsapp_sem_template: bool
    # Obrigatório para ligar: quem liga declara que leu o risco (suspensão/banimento do Direct Send pela Meta).
    confirmo_risco: bool = False


class DefinirTemplateWhatsAppRequestSchema(BaseModel):
    template_whatsapp_id: str


class RenomearCadenciaRequestSchema(BaseModel):
    nome: str


class DefinirCancelamentoAoResponderRequestSchema(BaseModel):
    cancelar_ao_responder: bool


class DefinirPausaEmpresaAoResponderRequestSchema(BaseModel):
    pausar_empresa_ao_responder: bool


class DefinirProspeccaoAutomaticaRequestSchema(BaseModel):
    prospeccao_automatica: bool


class CancelarCadenciaResponseSchema(BaseModel):
    cadencia: CadenciaSchema
    mensagens_canceladas: int


class AdicionarToqueRequestSchema(BaseModel):
    canal: str
    intervalo_dias_apos_anterior: int = 0
    template_whatsapp_id: str | None = None
    ab_teste_habilitado: bool = False


class AtualizarToqueRequestSchema(BaseModel):
    canal: str | None = None
    intervalo_dias_apos_anterior: int | None = None
    ab_teste_habilitado: bool | None = None


class CadenciaCreateSchema(BaseModel):
    nome: str
    toques: list[ToqueCadenciaCreateSchema]
    tipo: str = "prospeccao"
    # Opcional — só relevante pra quem tem mais de um ICP ativo ao mesmo
    # tempo (comparação de campanhas, `icp_service.performance`). Sem
    # informar, cai no ICP ativo (o primeiro encontrado, mesmo
    # comportamento de antes desta correção).
    icp_id: int | None = None
    # Cadência para uma lista de prospecção (sem ICP): gera mensagens só para as empresas dela. Não combina com `icp_id`.
    lista_prospeccao_id: int | None = None
    # Raio-X 2026-09-15: desligado por padrão — uma resposta do decisor
    # não interrompe mais a cadência a menos que isto seja marcado.
    cancelar_ao_responder: bool = False
    pausar_empresa_ao_responder: bool = False
    # Obrigatório quando algum toque de WhatsApp sai sem template (Direct Send): quem cria declara que leu o risco.
    direct_send_risco_aceito: bool = False


class GerarCadenciaRequestSchema(BaseModel):
    conta_ids: list[int]


class GerarCadenciaResponseSchema(BaseModel):
    contas_processadas: list[int]
    contas_sem_decisor: list[int]
    mensagens_geradas: int
    toques_bloqueados_restricao: int = 0
    toques_falha_ia: int = 0


class AtivarCadenciaResponseSchema(BaseModel):
    cadencia: CadenciaSchema
    franquia: dict


class VarianteAbSchema(BaseModel):
    total: int
    respondentes: int
    taxa_resposta: float


class RelatorioAbTesteSchema(BaseModel):
    variante_a: VarianteAbSchema
    variante_b: VarianteAbSchema
    z_score: float
    significativo: bool
    vencedora: str | None
