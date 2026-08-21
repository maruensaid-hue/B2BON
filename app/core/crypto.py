import base64
import hashlib

from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

_CHAVE_DEV_FIXA = base64.urlsafe_b64encode(hashlib.sha256(b"changeme-dev-configuracao-whatsapp-key").digest())


def obter_fernet() -> Fernet:
    """Fernet compartilhado pra criptografar campos sensíveis em repouso
    (ex.: credenciais Meta em `ConfiguracaoWhatsApp`). Chave real vem de
    `configuracao_whatsapp_encryption_key`; vazio em produção recusa —
    mesmo raciocínio do `cron_secret` (nunca abre exceção pra segredo
    vazio). Em dev/teste, cai numa chave fixa e determinística pra não
    exigir configuração local."""
    chave = settings.configuracao_whatsapp_encryption_key
    if not chave:
        if settings.e_ambiente_producao:
            raise RuntimeError(
                "CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY não configurada — obrigatória em "
                "produção pra criptografar credenciais do WhatsApp Business em repouso. "
                'Gere uma com `python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"`.'
            )
        return Fernet(_CHAVE_DEV_FIXA)
    return Fernet(chave.encode())


class TextoCriptografado(TypeDecorator):
    """Coluna de texto criptografada em repouso com Fernet — transparente
    pro ORM (lê/grava texto puro em memória), o banco só vê o token
    cifrado. Usar em qualquer coluna que guarde segredo/credencial de
    terceiro (ex.: access_token da Meta)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return obter_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return obter_fernet().decrypt(value.encode()).decode()
