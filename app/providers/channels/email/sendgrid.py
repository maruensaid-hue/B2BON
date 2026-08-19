import httpx

from app.core.config import settings
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio, montar_html_com_pixel

_URL_ENVIO = "https://api.sendgrid.com/v3/mail/send"


class SendGridEmailProvider(EmailProvider):
    """ESP real (raio-X de produção) — substitui o SMTP genérico. Envelope
    `From` fica fixo no domínio autenticado da plataforma (SPF/DKIM não dá
    pra fazer por tenant sem domínio próprio de cada um); `remetente_nome`/
    `remetente_email` configurados por tenant viram nome de exibição e
    `Reply-To`, então respostas ainda caem no lugar certo."""

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
        tenant_id: str,
        pixel_url: str | None = None,
    ) -> ResultadoEnvio:
        conteudo = [{"type": "text/plain", "value": corpo}]
        if pixel_url:
            conteudo.append({"type": "text/html", "value": montar_html_com_pixel(corpo, pixel_url)})

        corpo_requisicao = {
            "personalizations": [
                {
                    "to": [{"email": destinatario}],
                    # Ecoado de volta no Event Webhook — é assim que
                    # `sendgrid_webhook_service` sabe de qual tenant é um
                    # bounce/spam report chegado depois, de forma assíncrona.
                    "custom_args": {"tenant_id": tenant_id},
                }
            ],
            "from": {"email": settings.sendgrid_remetente_email, "name": remetente_nome},
            "reply_to": {"email": remetente_email},
            "subject": assunto,
            "content": conteudo,
        }

        try:
            resposta = httpx.post(
                _URL_ENVIO,
                json=corpo_requisicao,
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                timeout=15,
            )
        except httpx.HTTPError as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=str(erro))

        if resposta.status_code != 202:
            return ResultadoEnvio(sucesso=False, motivo_falha=f"SendGrid {resposta.status_code}: {resposta.text}")
        return ResultadoEnvio(sucesso=True, id_externo=resposta.headers.get("X-Message-Id"))
