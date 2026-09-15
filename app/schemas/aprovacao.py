from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AprovacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    mensagem_id: int
    status: str
    aprovador_id: str | None
    criado_em: datetime
    decidido_em: datetime | None


class AprovacaoFilaItemSchema(BaseModel):
    aprovacao_id: int
    status: str
    mensagem_id: int
    # Status da própria Mensagem (distinto do status da Aprovacao, que
    # fica "aprovado" pra sempre mesmo depois de enviada) — raio-X
    # 2026-09-15: é o que diferencia "aprovado, ainda não enviado" de
    # "já enviado" na tela de mensagens agendadas de um contato.
    mensagem_status: str
    canal: str
    template_id: str | None
    conteudo: str
    cadencia_id: int | None
    conta_id: int
    decisor_id: int
    agendado_para: datetime | None
    criado_em: datetime


class EditarMensagemRequestSchema(BaseModel):
    conteudo: str


class RejeitarRequestSchema(BaseModel):
    motivo: str | None = None


class AprovarLoteRequestSchema(BaseModel):
    ids: list[int]


class ExcluirLoteResponseSchema(BaseModel):
    excluidas: int


class RegraAutoAprovacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    template_id: str
    habilitada: bool


class DefinirRegraAutoAprovacaoRequestSchema(BaseModel):
    habilitada: bool
