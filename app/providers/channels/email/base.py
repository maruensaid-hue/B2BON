import html
from abc import ABC, abstractmethod

from pydantic import BaseModel


def montar_html_com_pixel(corpo: str, pixel_url: str) -> str:
    """HTML da parte `text/html` do multipart/alternative — texto puro
    escapado (preserva quebras de linha) mais o pixel de 1x1 de rastreio de
    abertura (Onda I). Compartilhado entre implementações reais de
    `EmailProvider` (SMTP, SendGrid) que precisam montar o mesmo corpo."""
    corpo_html = html.escape(corpo).replace("\n", "<br>")
    return (
        f'<html><body>{corpo_html}'
        f'<img src="{html.escape(pixel_url)}" width="1" height="1" alt="" style="display:none"></body></html>'
    )


class ResultadoEnvio(BaseModel):
    sucesso: bool
    id_externo: str | None = None
    motivo_falha: str | None = None


class EmailProvider(ABC):
    """Porta de envio de e-mail — isola o PREDATOR do provedor SMTP/ESP concreto."""

    @abstractmethod
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
    ) -> ResultadoEnvio:
        """`tenant_id` viaja até o provider pra permitir anexar contexto de
        tenant em eventos assíncronos do ESP (ex.: `custom_args` do SendGrid,
        ecoado de volta no Event Webhook — sem isso não dá pra saber de qual
        tenant é um bounce/spam report reportado depois do envio).

        `pixel_url`, quando presente, é o rastreio de abertura (Onda I) —
        exige mandar uma parte HTML do e-mail (texto puro não carrega
        imagem), então implementações reais devem enviar multipart/
        alternative com o pixel de 1x1 embutido na parte HTML.

        `mensagem_id`/`campanha_destinatario_id` (raio-X 2026-09-16, no
        máximo um dos dois presente, dependendo se o envio veio de
        cadência ou de campanha) — igual a `tenant_id`, viajam até o ESP
        (`custom_args`, só implementado no SendGrid) pra que um bounce
        assíncrono depois seja correlacionado à mensagem/destinatário
        exatos, não só ao tenant. Sem eles, o `sendgrid_webhook_service`
        só sabe pausar o canal inteiro, sem saber qual contato causou."""
        raise NotImplementedError
