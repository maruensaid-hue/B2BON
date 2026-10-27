import re

import httpx

from app.core.config import settings
from app.providers.channels.email.base import EmailProvider, ResultadoEnvio, montar_html_com_pixel

_URL_ENVIO = "https://api.sendgrid.com/v3/mail/send"


def _sem_nome_do_fornecedor(texto: str) -> str:
    """A mensagem de erro do serviço vai até a tela do cliente, e o nome do fornecedor não aparece em tela nem em dado visível."""
    return re.sub(r"(?i)sendgrid", "serviço de envio", texto)


class SendGridEmailProvider(EmailProvider):
    """ESP real (raio-X de produção) — substitui o SMTP genérico. Envelope
    `From` fica fixo no domínio autenticado da plataforma (SPF/DKIM não dá
    pra fazer por tenant sem domínio próprio de cada um); `remetente_nome`/
    `remetente_email` configurados por tenant viram nome de exibição e
    `Reply-To`, então respostas ainda caem no lugar certo."""

    def __init__(self, api_key: str | None = None, remetente_email: str | None = None, remetente_nome: str | None = None) -> None:
        """Sem argumentos usa a conta da plataforma (e-mail de sistema). Com a chave de API e o remetente do cliente (`ConfiguracaoEmailApi`), envia pela conta
        dele — o remetente precisa estar verificado no serviço dele — e o aviso de entrega/bounce volta com o `tenant_id` do cliente."""
        self.api_key = api_key
        self.remetente_email = remetente_email
        self.remetente_nome = remetente_nome

    def enviar(
        self,
        destinatario: str,
        assunto: str,
        corpo: str,
        remetente_nome: str,
        remetente_email: str,
        tenant_id: str,
        pixel_url: str | None = None,
        mensagem_id: int | None = None,
        campanha_destinatario_id: int | None = None,
        reply_to: str | None = None,
    ) -> ResultadoEnvio:
        conteudo = [{"type": "text/plain", "value": corpo}]
        if pixel_url:
            conteudo.append({"type": "text/html", "value": montar_html_com_pixel(corpo, pixel_url)})

        # Ecoados de volta no Event Webhook — é assim que
        # `sendgrid_webhook_service` sabe de qual tenant/mensagem/
        # destinatário é um bounce/spam report chegado depois, de forma
        # assíncrona (raio-X 2026-09-16: sem mensagem_id/campanha_
        # destinatario_id só dava pra pausar o canal, não saber o contato).
        custom_args = {"tenant_id": tenant_id}
        if mensagem_id is not None:
            custom_args["mensagem_id"] = str(mensagem_id)
        if campanha_destinatario_id is not None:
            custom_args["campanha_destinatario_id"] = str(campanha_destinatario_id)

        corpo_requisicao = {
            "personalizations": [
                {
                    "to": [{"email": destinatario}],
                    "custom_args": custom_args,
                }
            ],
            "from": {"email": self.remetente_email or settings.sendgrid_remetente_email, "name": self.remetente_nome or remetente_nome},
            "reply_to": {"email": reply_to or self.remetente_email or remetente_email},
            "subject": assunto,
            "content": conteudo,
        }

        try:
            resposta = httpx.post(
                _URL_ENVIO,
                json=corpo_requisicao,
                headers={"Authorization": f"Bearer {self.api_key or settings.sendgrid_api_key}"},
                timeout=15,
            )
        except httpx.HTTPError as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=str(erro), transitoria=True)

        if resposta.status_code != 202:
            return ResultadoEnvio(
                sucesso=False,
                motivo_falha=f"Falha do serviço de e-mail ({resposta.status_code}): {_sem_nome_do_fornecedor(resposta.text)}",
                transitoria=resposta.status_code == 429 or resposta.status_code >= 500,
            )
        return ResultadoEnvio(sucesso=True, id_externo=resposta.headers.get("X-Message-Id"))
