import pytest

from app.core.config import Settings


def test_producao_com_segredos_padrao_falha_ao_subir():
    """Vulnerabilidade real: sem esta trava, um deploy em produção com a
    env var JWT_SECRET_KEY esquecida sobe silenciosamente com o segredo
    visível no repositório — qualquer um forjaria um JWT de super_admin."""
    settings = Settings(database_url="postgresql://user:pass@host/db")

    with pytest.raises(RuntimeError, match="secret_key.*jwt_secret_key|jwt_secret_key.*secret_key"):
        settings.validar_segredos_de_producao()


def test_producao_com_segredos_fortes_sobe_normalmente():
    settings = Settings(
        database_url="postgresql://user:pass@host/db",
        secret_key="um-segredo-forte-gerado-de-verdade",
        jwt_secret_key="outro-segredo-forte-gerado-de-verdade",
    )

    settings.validar_segredos_de_producao()  # não deve lançar


def test_dev_sqlite_nao_bloqueia_mesmo_com_segredo_padrao():
    settings = Settings(database_url="sqlite:///./predator.db")

    settings.validar_segredos_de_producao()  # não deve lançar — dev/teste é permitido
