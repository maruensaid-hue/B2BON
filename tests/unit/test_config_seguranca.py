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
        redis_url="redis://localhost:6379/0",
    )

    settings.validar_segredos_de_producao()  # não deve lançar


def test_producao_sem_redis_compartilhado_falha_ao_subir():
    settings = Settings(
        database_url="postgresql://user:pass@host/db",
        secret_key="um-segredo-forte-gerado-de-verdade",
        jwt_secret_key="outro-segredo-forte-gerado-de-verdade",
    )

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        settings.validar_segredos_de_producao()


def test_dev_sqlite_nao_bloqueia_mesmo_com_segredo_padrao():
    settings = Settings(database_url="sqlite:///./predator.db")

    settings.validar_segredos_de_producao()  # não deve lançar — dev/teste é permitido


_FORTE = "Zk3vQ8mT1xLp9WcR5nB7dYh2JgU4aSeF6oIt0VqC"


def _producao(**segredos: str) -> Settings:
    base = {"database_url": "postgresql://user:pass@host/db", "redis_url": "redis://localhost:6379/0", "secret_key": _FORTE, "jwt_secret_key": _FORTE[::-1]}
    return Settings(**{**base, **segredos})


@pytest.mark.parametrize(
    "fraco",
    ["curto-demais", "a" * 40, "abababababababababababababababab", "changeme-" + "x1y2z3w4" * 4, "Password-" + "Zk3vQ8mT1xLp9WcR5nB7dYh2"],
)
def test_producao_recusa_jwt_fraco_curto_repetitivo_ou_obvio(fraco: str):
    """Auditoria A03: só o valor padrão era recusado; um JWT curto ou previsível passava e permitia forjar sessão."""
    with pytest.raises(RuntimeError, match="jwt_secret_key"):
        _producao(jwt_secret_key=fraco).validar_segredos_de_producao()


def test_producao_recusa_secret_key_fraca_sem_expor_o_valor():
    with pytest.raises(RuntimeError) as erro:
        _producao(secret_key="curto-demais").validar_segredos_de_producao()
    assert "secret_key" in str(erro.value)
    assert "curto-demais" not in str(erro.value)


def test_producao_recusa_mesmo_valor_nos_dois_segredos():
    with pytest.raises(RuntimeError, match="mesmo valor"):
        _producao(jwt_secret_key=_FORTE).validar_segredos_de_producao()


def test_producao_aceita_segredos_gerados_de_verdade():
    _producao().validar_segredos_de_producao()
