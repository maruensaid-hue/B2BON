from datetime import datetime

import httpx

from app.core.config import settings
from app.providers.meeting_bot.base import MeetingBotProvider


class RecallMeetingBotProvider(MeetingBotProvider):
    """Implementação real via Recall.ai (ou fornecedor equivalente de
    "meeting bot"). Raio-X: o formato exato de request/response abaixo
    segue a convenção de API mais comum desse tipo de serviço (endpoint
    `/bot`, `meeting_url`, `join_at`), mas precisa ser conferido contra a
    documentação real do fornecedor escolhido antes de ir pra produção —
    não há uma conta/chave real testada ainda nesta integração."""

    _BASE_URL = "https://api.recall.ai/api/v1"

    def _headers(self) -> dict:
        return {"Authorization": f"Token {settings.recall_api_key}", "Content-Type": "application/json"}

    def agendar_bot(self, link_reuniao: str, horario_inicio: datetime, webhook_url: str) -> str:
        resposta = httpx.post(
            f"{self._BASE_URL}/bot",
            json={
                "meeting_url": link_reuniao,
                "join_at": horario_inicio.isoformat(),
                "webhook_url": webhook_url,
            },
            headers=self._headers(),
            timeout=15.0,
        )
        resposta.raise_for_status()
        return resposta.json()["id"]
