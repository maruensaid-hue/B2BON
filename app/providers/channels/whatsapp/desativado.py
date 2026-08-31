from app.providers.channels.whatsapp.base import ResultadoEnvio, TemplateInfo, WhatsAppProvider


class WhatsAppDesativadoProvider(WhatsAppProvider):
    """No-op honesto pra produção sem `ConfiguracaoWhatsApp` do tenant
    (raio-X 2026-08-27) — mesmo raciocínio de `EmailDesativadoProvider`:
    diferente do `StubWhatsAppProvider` (dev/teste), que sempre reporta
    sucesso mesmo sem enviar nada de verdade. O número compartilhado da
    plataforma deixou de existir como fallback — cada tenant precisa da
    própria conta Meta pra disparar WhatsApp."""

    _MOTIVO = "Envio de WhatsApp não está configurado para este tenant."

    def enviar_template(self, telefone: str, template_id: str, variaveis: dict) -> ResultadoEnvio:
        return ResultadoEnvio(sucesso=False, motivo_falha=self._MOTIVO)

    def enviar_texto_livre(self, telefone: str, texto: str) -> ResultadoEnvio:
        return ResultadoEnvio(sucesso=False, motivo_falha=self._MOTIVO)

    def listar_templates(self) -> list[TemplateInfo]:
        return []
