import time
from collections import defaultdict
from threading import Lock

from fastapi import Request

from app.services.errors import LimiteDeTaxaExcedido


class LimitadorEmMemoria:
    """Janela deslizante por processo — suficiente hoje porque a API roda
    numa única instância Render (Onda raio-X); se algum dia escalar
    horizontalmente, isto precisa virar um backend compartilhado (Redis)
    para o limite valer entre instâncias."""

    def __init__(self) -> None:
        self._tentativas: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def checar(self, chave: str, max_tentativas: int, janela_segundos: int) -> None:
        agora = time.monotonic()
        with self._lock:
            tentativas = self._tentativas[chave]
            limite_inferior = agora - janela_segundos
            tentativas[:] = [instante for instante in tentativas if instante > limite_inferior]
            if len(tentativas) >= max_tentativas:
                raise LimiteDeTaxaExcedido("Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.")
            tentativas.append(agora)

    def resetar(self) -> None:
        """Só para teste — evita que o estado de um teste vaze pro próximo
        (a suíte inteira roda no mesmo processo)."""
        with self._lock:
            self._tentativas.clear()


limitador_auth = LimitadorEmMemoria()

# Bucket separado do de auth (Fase 2 da hierarquia, raio-X) — tráfego de
# parceiro (chave de API) não deve competir por cota com tentativas de
# login/registro, são naturezas de abuso bem diferentes.
limitador_parceiros = LimitadorEmMemoria()


def limitar_por_ip(max_tentativas: int = 5, janela_segundos: int = 300):
    """Dependency factory — protege rotas públicas de autenticação contra
    força bruta (login) e criação em massa (registro), sem exigir
    infraestrutura nova."""

    def _dependencia(request: Request) -> None:
        ip = request.client.host if request.client else "desconhecido"
        limitador_auth.checar(f"{request.url.path}:{ip}", max_tentativas, janela_segundos)

    return _dependencia
