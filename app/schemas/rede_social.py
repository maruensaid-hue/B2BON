from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PerfilEmpresaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    nome_exibicao: str
    descricao: str | None
    setor: str | None
    site: str | None
    logo_url: str | None
    capa_url: str | None
    cnae_principal: str | None
    porte: str | None
    sede_cidade: str | None
    sede_uf: str | None
    mercados: list[str]
    produtos_servicos: list[str]
    tecnologias: list[str]
    certificacoes: list[str]
    redes_sociais: dict[str, str]
    status_verificacao: str
    criado_em: datetime
    atualizado_em: datetime


class AtualizarPerfilRequestSchema(BaseModel):
    nome_exibicao: str | None = None
    descricao: str | None = None
    setor: str | None = None
    site: str | None = None
    logo_url: str | None = None
    capa_url: str | None = None
    cnae_principal: str | None = None
    porte: str | None = None
    sede_cidade: str | None = None
    sede_uf: str | None = None
    mercados: list[str] | None = None
    produtos_servicos: list[str] | None = None
    tecnologias: list[str] | None = None
    certificacoes: list[str] | None = None
    redes_sociais: dict[str, str] | None = None


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
