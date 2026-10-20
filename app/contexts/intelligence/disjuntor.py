"""Instância do disjuntor do gateway de IA (a classe genérica vive em `app.core.disjuntor`).

Provedor fora do ar não pode custar um timeout de 25 s por chamada nem martelar o serviço. Depois de `ai_disjuntor_falhas`
falhas SEGUIDAS do provedor o circuito abre: as chamadas falham na hora com `IAIndisponivel`. Passada a pausa, UMA chamada
de teste é liberada (meio-aberto); se ela der certo o circuito fecha, se falhar reabre pela pausa inteira.

Estado em memória do processo (cada instância tem o seu): suficiente para proteger contra tempestade de chamadas e
barato; o núcleo determinístico do produto nunca passa por aqui.
"""

from app.core.disjuntor import Disjuntor

disjuntor_ia = Disjuntor()

__all__ = ["Disjuntor", "disjuntor_ia"]
