import httpx

from app.core.config import settings
from app.providers.channels.whatsapp.base import ResultadoEnvio, TemplateInfo, WhatsAppProvider


class MetaWhatsAppProvider(WhatsAppProvider):
    """Implementação real via Graph API da Meta — WhatsApp Business API oficial."""

    _BASE_URL = "https://graph.facebook.com/v20.0"

    def __init__(self) -> None:
        self._token = settings.whatsapp_access_token
        self._phone_number_id = settings.whatsapp_phone_number_id
        self._waba_id = settings.whatsapp_business_account_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def enviar_template(self, telefone: str, template_id: str, variaveis: dict) -> ResultadoEnvio:
        payload = {
            "messaging_product": "whatsapp",
            "to": telefone,
            "type": "template",
            "template": {
                "name": template_id,
                "language": {"code": "pt_BR"},
                "components": (
                    [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": str(v)} for v in variaveis.values()],
                        }
                    ]
                    if variaveis
                    else []
                ),
            },
        }
        return self._enviar(payload)

    def enviar_texto_livre(self, telefone: str, texto: str) -> ResultadoEnvio:
        payload = {
            "messaging_product": "whatsapp",
            "to": telefone,
            "type": "text",
            "text": {"body": texto},
        }
        return self._enviar(payload)

    def _enviar(self, payload: dict) -> ResultadoEnvio:
        try:
            resposta = httpx.post(
                f"{self._BASE_URL}/{self._phone_number_id}/messages",
                json=payload,
                headers=self._headers(),
                timeout=15.0,
            )
            resposta.raise_for_status()
            corpo = resposta.json()
            id_externo = corpo.get("messages", [{}])[0].get("id")
            return ResultadoEnvio(sucesso=True, id_externo=id_externo)
        except httpx.HTTPError as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=str(erro))

    def listar_templates(self) -> list[TemplateInfo]:
        try:
            resposta = httpx.get(
                f"{self._BASE_URL}/{self._waba_id}/message_templates",
                headers=self._headers(),
                timeout=15.0,
            )
            resposta.raise_for_status()
            dados = resposta.json().get("data", [])
            return [
                TemplateInfo(
                    nome=item["name"],
                    status=item["status"].lower(),
                    corpo=next(
                        (c["text"] for c in item.get("components", []) if c.get("type") == "BODY"), ""
                    ),
                )
                for item in dados
            ]
        except httpx.HTTPError:
            return []
