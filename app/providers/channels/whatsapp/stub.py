from app.providers.channels.whatsapp.base import ResultadoEnvio, TemplateInfo, WhatsAppProvider


class StubWhatsAppProvider(WhatsAppProvider):
    """Sempre "enviado" — usado em dev enquanto não há credenciais Meta reais
    e em todo teste (a implementação real fica em `MetaWhatsAppProvider`)."""

    def __init__(self) -> None:
        self.envios: list[dict] = []

    def enviar_template(
        self, telefone: str, template_id: str, variaveis: dict, variavel_botao: str | None = None
    ) -> ResultadoEnvio:
        self.envios.append(
            {"telefone": telefone, "template_id": template_id, "variaveis": variaveis, "variavel_botao": variavel_botao}
        )
        return ResultadoEnvio(sucesso=True, id_externo=f"stub-{len(self.envios)}")

    def enviar_texto_livre(self, telefone: str, texto: str) -> ResultadoEnvio:
        self.envios.append({"telefone": telefone, "texto": texto})
        return ResultadoEnvio(sucesso=True, id_externo=f"stub-{len(self.envios)}")

    def listar_templates(self) -> list[TemplateInfo]:
        return [TemplateInfo(nome="prospeccao_inicial", status="aprovado", corpo="Olá {{1}}, tudo bem?")]
