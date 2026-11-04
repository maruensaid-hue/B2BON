from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfiguracaoWhatsAppSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    phone_number_id: str
    business_account_id: str
    access_token_mascarado: str
    origem_conexao: str | None = None
    numero_exibicao: str | None = None
    nome_verificado: str | None = None
    qualidade: str | None = None
    token_expira_em: datetime | None = None
    direct_send_habilitado: bool = False
    direct_send_motivo_desligado: str | None = None
    criado_em: datetime
    atualizado_em: datetime


class ConfiguracaoWhatsAppUpsertSchema(BaseModel):
    phone_number_id: str
    business_account_id: str
    access_token: str | None = None


class ConectarMetaRequestSchema(BaseModel):
    codigo: str = ""
    access_token: str | None = None  # configuração do tipo "token de acesso do usuário": a janela devolve o token, não um código
    phone_number_id: str
    business_account_id: str
    pagina: str | None = None  # endereço da tela onde o botão foi clicado (a Meta pode exigir como redirect_uri na troca do código)


class DefinirDirectSendRequestSchema(BaseModel):
    habilitado: bool
