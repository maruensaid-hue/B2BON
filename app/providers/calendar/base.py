from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class EventoCalendario(BaseModel):
    id_externo: str
    link_reuniao: str


class CalendarProvider(ABC):
    """Porta de integração com a agenda do vendedor — Google Calendar no MVP (E6-H1)."""

    @abstractmethod
    def propor_horarios(
        self, inicio_janela: datetime, fim_janela: datetime, duracao_minutos: int = 30
    ) -> list[datetime]:
        raise NotImplementedError

    @abstractmethod
    def criar_evento(
        self, titulo: str, inicio: datetime, fim: datetime, participantes: list[str], descricao: str
    ) -> EventoCalendario:
        raise NotImplementedError

    @abstractmethod
    def cancelar_evento(self, id_externo: str) -> None:
        raise NotImplementedError
