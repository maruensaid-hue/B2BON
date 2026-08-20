from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import settings
from app.providers.meeting_bot.recall import RecallMeetingBotProvider

_REQUEST_FALSO = httpx.Request("POST", "https://api.recall.ai/api/v1/bot")


@pytest.fixture(autouse=True)
def _config_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "recall_api_key", "chave-de-teste-recall")


def test_agendar_bot_retorna_id_externo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={"id": "bot-abc"}, request=_REQUEST_FALSO))

    bot_id = RecallMeetingBotProvider().agendar_bot(
        "https://meet.google.com/xyz-abcd-efg", datetime(2026, 9, 1, 14, 0, tzinfo=UTC), "https://api.b2bon.com.br/webhooks/recall/eventos"
    )

    assert bot_id == "bot-abc"


def test_agendar_bot_envia_link_horario_e_webhook_no_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado = {}

    def _post_falso(url, json, headers, timeout):
        capturado.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"id": "bot-xyz"}, request=_REQUEST_FALSO)

    monkeypatch.setattr(httpx, "post", _post_falso)
    horario = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)

    RecallMeetingBotProvider().agendar_bot(
        "https://meet.google.com/xyz-abcd-efg", horario, "https://api.b2bon.com.br/webhooks/recall/eventos"
    )

    assert capturado["json"]["meeting_url"] == "https://meet.google.com/xyz-abcd-efg"
    assert capturado["json"]["join_at"] == horario.isoformat()
    assert capturado["json"]["webhook_url"] == "https://api.b2bon.com.br/webhooks/recall/eventos"
    assert capturado["headers"]["Authorization"] == "Token chave-de-teste-recall"


def test_erro_http_propaga(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, json={"detail": "unauthorized"}, request=_REQUEST_FALSO))

    with pytest.raises(httpx.HTTPStatusError):
        RecallMeetingBotProvider().agendar_bot(
            "https://meet.google.com/xyz-abcd-efg", datetime(2026, 9, 1, 14, 0, tzinfo=UTC), "https://api.b2bon.com.br/webhooks/recall/eventos"
        )
