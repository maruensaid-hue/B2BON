import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import rate_limit
from app.core.config import settings
from app.services.errors import LimiteDeTaxaExcedido


class FakeRedis:
    def __init__(self, resultado=1, erro=None):
        self.resultado = resultado
        self.erro = erro
        self.chamadas = []

    def eval(self, *args):
        self.chamadas.append(args)
        if self.erro:
            raise self.erro
        return self.resultado


def test_rate_limit_usa_script_redis_compartilhado(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(settings, "redis_url", "redis://redis.example:6379/0")
    monkeypatch.setattr(rate_limit.Redis, "from_url", lambda *args, **kwargs: fake)
    limitador = rate_limit.LimitadorEmMemoria()

    limitador.checar("login:203.0.113.10", 5, 300)

    assert len(fake.chamadas) == 1
    chamada = fake.chamadas[0]
    assert chamada[1] == 1
    assert chamada[2] == "b2bon:ratelimit:login:203.0.113.10"
    assert "ZREMRANGEBYSCORE" in chamada[0]


def test_rate_limit_nega_tentativa_se_redis_falhar(monkeypatch):
    fake = FakeRedis(erro=RedisConnectionError("indisponível"))
    monkeypatch.setattr(settings, "redis_url", "redis://redis.example:6379/0")
    monkeypatch.setattr(rate_limit.Redis, "from_url", lambda *args, **kwargs: fake)
    limitador = rate_limit.LimitadorEmMemoria()

    with pytest.raises(LimiteDeTaxaExcedido, match="Proteção temporariamente indisponível"):
        limitador.checar("login:203.0.113.10", 5, 300)


def test_rate_limit_em_memoria_limita_tentativas_sem_redis(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    limitador = rate_limit.LimitadorEmMemoria()

    limitador.checar("login:local", 1, 300)
    with pytest.raises(LimiteDeTaxaExcedido, match="Muitas tentativas"):
        limitador.checar("login:local", 1, 300)
