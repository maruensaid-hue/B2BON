from abc import ABC, abstractmethod
from datetime import datetime


class MeetingBotProvider(ABC):
    """Porta de integração com um serviço de "meeting bot" terceiro (raio-X
    — tipo Recall.ai) — o bot entra no link da reunião de vídeo e grava/
    transcreve, sem depender do Google Workspace de quem organiza (a
    integração de calendário hoje usa um token global único da B2B ON, não
    OAuth por tenant/vendedor — ver `app/providers/calendar/google.py`)."""

    @abstractmethod
    def agendar_bot(self, link_reuniao: str, horario_inicio: datetime, webhook_url: str) -> str:
        """Agenda o bot pra entrar na reunião no horário combinado. Devolve
        o `bot_id` externo — é por ele que o webhook de callback casa o
        evento de volta com a `Reuniao` certa."""
        raise NotImplementedError
