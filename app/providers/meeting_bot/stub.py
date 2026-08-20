from datetime import datetime

from app.providers.meeting_bot.base import MeetingBotProvider


class StubMeetingBotProvider(MeetingBotProvider):
    """Bot determinístico, sem rede — dev/teste."""

    def __init__(self) -> None:
        self.bots_agendados: list[dict] = []

    def agendar_bot(self, link_reuniao: str, horario_inicio: datetime, webhook_url: str) -> str:
        bot_id = f"stub-bot-{len(self.bots_agendados) + 1}"
        self.bots_agendados.append(
            {"bot_id": bot_id, "link_reuniao": link_reuniao, "horario_inicio": horario_inicio, "webhook_url": webhook_url}
        )
        return bot_id
