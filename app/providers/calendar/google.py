from datetime import datetime, timedelta

import httpx

from app.core.config import settings
from app.providers.calendar.base import CalendarProvider, EventoCalendario


class GoogleCalendarProvider(CalendarProvider):
    """Implementação real via Google Calendar API v3 (Bearer token)."""

    _BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(self) -> None:
        self._token = settings.google_calendar_access_token
        self._calendar_id = settings.google_calendar_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def propor_horarios(
        self, inicio_janela: datetime, fim_janela: datetime, duracao_minutos: int = 30
    ) -> list[datetime]:
        try:
            resposta = httpx.post(
                f"{self._BASE_URL}/freeBusy",
                json={
                    "timeMin": inicio_janela.isoformat(),
                    "timeMax": fim_janela.isoformat(),
                    "items": [{"id": self._calendar_id}],
                },
                headers=self._headers(),
                timeout=15.0,
            )
            resposta.raise_for_status()
            ocupados = resposta.json()["calendars"][self._calendar_id]["busy"]
        except httpx.HTTPError:
            ocupados = []

        candidatos: list[datetime] = []
        cursor = inicio_janela
        duracao = timedelta(minutes=duracao_minutos)
        while cursor + duracao <= fim_janela and len(candidatos) < 3:
            fim_slot = cursor + duracao
            conflita = any(
                cursor < datetime.fromisoformat(bloco["end"]) and fim_slot > datetime.fromisoformat(bloco["start"])
                for bloco in ocupados
            )
            if not conflita:
                candidatos.append(cursor)
            cursor += duracao
        return candidatos

    def criar_evento(
        self, titulo: str, inicio: datetime, fim: datetime, participantes: list[str], descricao: str
    ) -> EventoCalendario:
        payload = {
            "summary": titulo,
            "description": descricao,
            "start": {"dateTime": inicio.isoformat()},
            "end": {"dateTime": fim.isoformat()},
            "attendees": [{"email": participante} for participante in participantes],
            "conferenceData": {"createRequest": {"requestId": titulo}},
        }
        resposta = httpx.post(
            f"{self._BASE_URL}/calendars/{self._calendar_id}/events",
            json=payload,
            headers=self._headers(),
            params={"conferenceDataVersion": 1},
            timeout=15.0,
        )
        resposta.raise_for_status()
        corpo = resposta.json()
        link = corpo.get("hangoutLink") or corpo.get("htmlLink", "")
        return EventoCalendario(id_externo=corpo["id"], link_reuniao=link)

    def cancelar_evento(self, id_externo: str) -> None:
        httpx.delete(
            f"{self._BASE_URL}/calendars/{self._calendar_id}/events/{id_externo}",
            headers=self._headers(),
            timeout=15.0,
        )
