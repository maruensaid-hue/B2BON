import logging

import httpx

from app.core.config import settings
from app.providers.channels.whatsapp.base import InfoNumero, ResultadoEnvio, TemplateCriado, TemplateInfo, WhatsAppProvider

logger = logging.getLogger(__name__)


class MetaWhatsAppProvider(WhatsAppProvider):
    """Implementação real via Graph API da Meta — WhatsApp Business API
    oficial. Credenciais explícitas no construtor (não lidas de
    `settings` global) desde o raio-X de produção — o número de WhatsApp
    é por tenant, não compartilhado por toda a plataforma, e cada
    instância desta classe fala com um número específico."""

    def __init__(self, access_token: str, phone_number_id: str, business_account_id: str) -> None:
        # Lida na criação (não no import): segue a versão configurada, inclusive em teste.
        self._base_url = f"https://graph.facebook.com/{settings.meta_graph_versao}"
        self._token = access_token
        self._phone_number_id = phone_number_id
        self._waba_id = business_account_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def enviar_template(
        self, telefone: str, template_id: str, variaveis: dict, variavel_botao: str | None = None
    ) -> ResultadoEnvio:
        components = (
            [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in variaveis.values()]}]
            if variaveis
            else []
        )
        if variavel_botao:
            # Raio-X 2026-09-15: preenche a URL dinâmica de um botão
            # "Visitar site" do template (ex.: "https://wa.me/{{1}}") —
            # o template com o botão em si é cadastrado pelo próprio
            # tenant direto no WhatsApp Manager da Meta; aqui só
            # preenchemos a variável na hora do envio.
            components.append(
                {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": variavel_botao}]}
            )
        payload = {
            "messaging_product": "whatsapp",
            "to": telefone,
            "type": "template",
            "template": {
                "name": template_id,
                "language": {"code": "pt_BR"},
                "components": components,
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

    def enviar_direct_send(self, telefone: str, texto: str, categoria: str = "utility") -> ResultadoEnvio:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefone,
            "type": "text",
            "text": {"body": texto},
            "category": categoria,
        }
        return self._enviar(payload)

    def _enviar(self, payload: dict) -> ResultadoEnvio:
        try:
            resposta = httpx.post(
                f"{self._base_url}/{self._phone_number_id}/messages",
                json=payload,
                headers=self._headers(),
                timeout=15.0,
            )
        except httpx.HTTPError as erro:
            return ResultadoEnvio(sucesso=False, motivo_falha=f"Sem resposta da Meta ({type(erro).__name__}).")
        if resposta.is_success:
            id_externo = resposta.json().get("messages", [{}])[0].get("id")
            return ResultadoEnvio(sucesso=True, id_externo=id_externo)
        return _falha_meta(resposta)

    def listar_templates(self) -> list[TemplateInfo]:
        try:
            resposta = httpx.get(
                f"{self._base_url}/{self._waba_id}/message_templates",
                headers=self._headers(),
                timeout=15.0,
            )
            if not resposta.is_success:
                # Antes a falha sumia (lista vazia, sem motivo): agora fica no log com o código da Meta.
                logger.warning("META_LISTAR_TEMPLATES_FALHOU status=%s motivo=%s", resposta.status_code, _falha_meta(resposta).motivo_falha)
                return []
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
        except httpx.HTTPError as erro:
            logger.warning("META_LISTAR_TEMPLATES_FALHOU sem_resposta=%s", type(erro).__name__)
            return []

    def criar_template(self, nome: str, categoria: str, corpo: str, rodape: str | None = None) -> TemplateCriado:
        # pt_BR: o envio (`enviar_template`) sempre pede o idioma pt_BR, então o modelo nasce nele.
        componentes: list[dict] = [{"type": "BODY", "text": corpo}]
        if rodape:
            componentes.append({"type": "FOOTER", "text": rodape})
        try:
            resposta = httpx.post(
                f"{self._base_url}/{self._waba_id}/message_templates",
                json={"name": nome, "language": "pt_BR", "category": categoria, "components": componentes},
                headers=self._headers(),
                timeout=15.0,
            )
        except httpx.HTTPError as erro:
            return TemplateCriado(erro=f"Sem resposta da Meta ({type(erro).__name__}).")
        if not resposta.is_success:
            return TemplateCriado(erro=_falha_meta(resposta).motivo_falha)
        dados = resposta.json()
        return TemplateCriado(id_externo=dados.get("id"), status=(dados.get("status") or "PENDING").lower())

    def info_numero(self) -> InfoNumero:
        try:
            resposta = httpx.get(
                f"{self._base_url}/{self._phone_number_id}",
                params={"fields": "display_phone_number,verified_name,quality_rating"},
                headers=self._headers(),
                timeout=15.0,
            )
        except httpx.HTTPError as erro:
            return InfoNumero(erro=f"Sem resposta da Meta ({type(erro).__name__}).")
        if not resposta.is_success:
            return InfoNumero(erro=_falha_meta(resposta).motivo_falha)
        dados = resposta.json()
        return InfoNumero(
            numero_exibicao=dados.get("display_phone_number"), nome_verificado=dados.get("verified_name"),
            qualidade=dados.get("quality_rating"),
        )


def _falha_meta(resposta: httpx.Response) -> ResultadoEnvio:
    """Erro da Graph API com código e mensagem da própria Meta (antes só "400 Bad Request", impossível de diagnosticar)."""
    try:
        erro = resposta.json().get("error", {})
    except ValueError:
        erro = {}
    codigo = erro.get("code")
    mensagem = erro.get("error_user_msg") or erro.get("message") or f"HTTP {resposta.status_code}"
    return ResultadoEnvio(sucesso=False, codigo_erro=codigo if isinstance(codigo, int) else None,
                          motivo_falha=f"Meta recusou ({codigo}): {mensagem}"[:500])

