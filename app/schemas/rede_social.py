from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PerfilEmpresaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    nome_exibicao: str
    descricao: str | None
    setor: str | None
    site: str | None
    criado_em: datetime
    atualizado_em: datetime


class AtualizarPerfilRequestSchema(BaseModel):
    nome_exibicao: str | None = None
    descricao: str | None = None
    setor: str | None = None
    site: str | None = None


class OfertaResumoSchema(BaseModel):
    nome: str
    descricao: str


class EmpresaDiretorioSchema(BaseModel):
    perfil: PerfilEmpresaSchema
    status_conexao: str  # nenhuma | pendente_enviada | pendente_recebida | aceita
    oferta_principal: OfertaResumoSchema | None


class ConexaoEmpresaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id_origem: str
    tenant_id_destino: str
    status: str
    criado_em: datetime
    respondida_em: datetime | None


class SolicitarConexaoRequestSchema(BaseModel):
    tenant_id_destino: str


class ResponderConexaoRequestSchema(BaseModel):
    aceitar: bool


class MensagemRedeSocialSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id_remetente: str
    tenant_id_destinatario: str
    usuario_remetente_id: int | None
    texto: str
    lida_em: datetime | None
    criado_em: datetime


class EnviarMensagemRequestSchema(BaseModel):
    tenant_id_destinatario: str
    texto: str
