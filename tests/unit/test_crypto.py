import pytest

from app.core.config import Settings
from app.core.crypto import TextoCriptografado, obter_fernet


def test_obter_fernet_em_dev_usa_chave_fixa_determinística():
    fernet = obter_fernet()

    token = fernet.encrypt(b"segredo")
    assert fernet.decrypt(token) == b"segredo"


def test_producao_sem_chave_de_criptografia_recusa(monkeypatch):
    settings = Settings(database_url="postgresql://user:pass@host/db")
    monkeypatch.setattr("app.core.crypto.settings", settings)

    with pytest.raises(RuntimeError, match="CONFIGURACAO_WHATSAPP_ENCRYPTION_KEY"):
        obter_fernet()


def test_producao_com_chave_configurada_nao_recusa(monkeypatch):
    from cryptography.fernet import Fernet

    chave = Fernet.generate_key().decode()
    settings = Settings(database_url="postgresql://user:pass@host/db", configuracao_whatsapp_encryption_key=chave)
    monkeypatch.setattr("app.core.crypto.settings", settings)

    fernet = obter_fernet()
    assert fernet.decrypt(fernet.encrypt(b"segredo")) == b"segredo"


def test_texto_criptografado_process_bind_e_result_fazem_roundtrip():
    tipo = TextoCriptografado()

    cifrado = tipo.process_bind_param("segredo-original", dialect=None)
    assert cifrado != "segredo-original"

    decifrado = tipo.process_result_value(cifrado, dialect=None)
    assert decifrado == "segredo-original"


def test_texto_criptografado_aceita_none():
    tipo = TextoCriptografado()

    assert tipo.process_bind_param(None, dialect=None) is None
    assert tipo.process_result_value(None, dialect=None) is None
