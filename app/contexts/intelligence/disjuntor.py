"""Disjuntor (circuit breaker) do provedor de IA.

Provedor fora do ar não pode custar um timeout de 25 s por chamada nem martelar o serviço. Depois de `ai_disjuntor_falhas`
falhas SEGUIDAS do provedor o circuito abre: as chamadas falham na hora com `IAIndisponivel`. Passada a pausa, UMA chamada
de teste é liberada (meio-aberto); se ela der certo o circuito fecha, se falhar reabre pela pausa inteira.

Estado em memória do processo (cada instância tem o seu): suficiente para proteger contra tempestade de chamadas e
barato; o núcleo determinístico do produto nunca passa por aqui.
"""

import threading
import time
from collections.abc import Callable

from app.core.config import settings


class Disjuntor:
    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._trava = threading.Lock()
        self._falhas = 0
        self._aberto_ate: float | None = None

    @staticmethod
    def _limite() -> int:
        return settings.ai_disjuntor_falhas

    def permite(self) -> bool:
        if self._limite() <= 0:
            return True
        with self._trava:
            if self._aberto_ate is None:
                return True
            agora = self._relogio()
            if agora < self._aberto_ate:
                return False
            # Meio-aberto: libera uma chamada de teste e segura as demais pela pausa.
            self._aberto_ate = agora + settings.ai_disjuntor_pausa_segundos
            return True

    def sucesso(self) -> None:
        with self._trava:
            self._falhas = 0
            self._aberto_ate = None

    def falha(self) -> None:
        if self._limite() <= 0:
            return
        with self._trava:
            self._falhas += 1
            if self._falhas >= self._limite():
                self._aberto_ate = self._relogio() + settings.ai_disjuntor_pausa_segundos

    def aberto(self) -> bool:
        with self._trava:
            return self._aberto_ate is not None and self._relogio() < self._aberto_ate

    def reiniciar(self) -> None:
        self.sucesso()


disjuntor_ia = Disjuntor()
