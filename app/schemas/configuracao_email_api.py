from datetime import datetime

from pydantic import BaseModel


class ConfiguracaoEmailApiSchema(BaseModel):
    """Configuração do envio por API devolvida ao cliente: chave mascarada e o endereço dos avisos de entrega."""
    id: int
    tenant_id: str
    remetente_email: str
    remetente_nome: str | None
    chave_mascarada: str
    tem_chave_webhook: bool
    # Endereço que o cliente informa no serviço de envio dele para receber os avisos de entrega, bounce e spam.
    url_webhook: str
    criado_em: datetime
    atualizado_em: datetime


class ConfiguracaoEmailApiUpsertSchema(BaseModel):
    """Dados para salvar o envio por API; chave em branco mantém a atual."""
    chave_api: str | None = None
    remetente_email: str
    remetente_nome: str | None = None
    chave_webhook: str | None = None
