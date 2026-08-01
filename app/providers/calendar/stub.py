from datetime import datetime, timedelta

from app.providers.calendar.base import CalendarProvider, EventoCalendario


class StubCalendarProvider(CalendarProvider):
    """Horários determinísticos, sem Google real — dev/teste."""

    def __init__(self) -> None:
        self.eventos_criados: list[dict] = []
        self.eventos_cancelados: list[str] = []

    def propor_horarios(
        self, inicio_janela: datetime, fim_janela: datetime, duracao_minutos: int = 30
    ) -> list[datetime]:
        return [inicio_janela + timedelta(hours=deslocamento) for deslocamento in (1, 24, 25)][:3]

    def criar_evento(
        self, titulo: str, inicio: datetime, fim: datetime, participantes: list[str], descricao: str
    ) -> EventoCalendario:
        id_externo = f"stub-evento-{len(self.eventos_criados) + 1}"
        self.eventos_criados.append(
            {"id_externo": id_externo, "titulo": titulo, "inicio": inicio, "participantes": participantes}
        )
        return EventoCalendario(id_externo=id_externo, link_reuniao=f"https://meet.stub/{id_externo}")

    def cancelar_evento(self, id_externo: str) -> None:
        self.eventos_cancelados.append(id_externo)
