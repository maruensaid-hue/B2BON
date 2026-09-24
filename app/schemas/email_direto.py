from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmailDiretoCreateSchema(BaseModel):
    decisor_id: int
    assunto: str
    corpo: str


class EmailDiretoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decisor_id: int
    decisor_nome: str
    decisor_email: str | None
    conta_id: int
    conta_nome: str
    remetente_usuario_id: int
    remetente_nome: str
    assunto: str
    corpo: str
    status: str
    motivo_falha: str | None
    enviado_em: datetime | None
    criado_em: datetime


class ConfiguracaoEmailAgenteSchema(BaseModel):
    email_nome_exibicao: str | None
    email_assinatura: str | None


class AtualizarConfiguracaoEmailAgenteRequestSchema(BaseModel):
    email_nome_exibicao: str | None = None
    email_assinatura: str | None = None


class EmailRecebidoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decisor_id: int | None
    decisor_nome: str | None
    conta_id: int | None
    conta_nome: str | None
    remetente_email: str
    assunto: str
    corpo: str
    criado_em: datetime


class ArquivarConversaRequestSchema(BaseModel):
    decisor_id: int


class ArquivarConversaResponseSchema(BaseModel):
    enviados_arquivados: int
    recebidos_arquivados: int


class PendenteArquivamentoSchema(BaseModel):
    decisor_id: int
    decisor_nome: str
    conta_nome: str
    total_enviados: int
    total_recebidos: int
