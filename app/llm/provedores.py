"""Adapters de provedores adicionais de IA (Cloudflare Workers AI, Groq, OpenRouter, Google Gemini).

Todos implementam `LLMProvider` e seguem o mesmo contrato do `ClaudeProvider`:

* falha DO PROVEDOR (rede, timeout, 429, 5xx, 400/401/403/404, corpo ilegível) → `LLMFalhaDeProvedor` (alimenta disjuntor e fallback);
* provedor respondeu mas sem texto utilizável (vazio, cortado por limite de tokens) → `LLMIndisponivel` (não troca de provedor);
* nunca coloca a chave em mensagem de erro, URL ou log; a chave vai só em cabeçalho;
* o `model` do `LLMRequest` é o id de modelo da Anthropic escolhido pelo roteador do gateway e **nunca** vale para estes adapters:
  cada um usa o modelo configurado por variável de ambiente.

Estado de cada adapter (ver `docs/b2bon/PROVEDORES_IA.md`): implementado e testado com respostas simuladas (httpx.MockTransport);
**nenhum foi testado contra o serviço real** (sem credenciais) e nenhum está habilitado por padrão.
"""

import httpx

from app.llm.base import LLMFalhaDeProvedor, LLMIndisponivel, LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse


class _ProvedorHttp(LLMProvider):
    id: str = ""

    def __init__(self, *, chave: str, modelo: str, timeout: float = 25.0, transport: httpx.BaseTransport | None = None) -> None:
        self._chave, self._modelo = chave, modelo
        self._cliente = httpx.Client(timeout=timeout, transport=transport, trust_env=False, follow_redirects=False)

    def _post(self, url: str, cabecalhos: dict[str, str], corpo: dict) -> dict:
        try:
            resposta = self._cliente.post(url, headers=cabecalhos, json=corpo)
        except httpx.HTTPError as erro:
            raise LLMFalhaDeProvedor(f"{self.id}: falha de rede ({type(erro).__name__}).") from erro
        if resposta.status_code != 200:
            raise LLMFalhaDeProvedor(f"{self.id} respondeu {resposta.status_code}.")
        try:
            dados = resposta.json()
        except ValueError as erro:
            raise LLMFalhaDeProvedor(f"{self.id} devolveu uma resposta que não é JSON válido.") from erro
        if not isinstance(dados, dict):
            raise LLMFalhaDeProvedor(f"{self.id} devolveu uma resposta fora do formato esperado.")
        return dados

    def _texto_valido(self, texto: object) -> str:
        if not isinstance(texto, str) or not texto.strip():
            raise LLMIndisponivel(f"{self.id}: a IA não retornou texto na resposta.")
        return texto


class OpenAICompativel(_ProvedorHttp):
    """Chat completions no formato OpenAI: usado por Groq e OpenRouter (mesmo contrato, URL e cabeçalhos diferentes)."""

    def __init__(self, *, id: str, url: str, cabecalhos_extras: dict[str, str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.id, self._url, self._extras = id, url, cabecalhos_extras or {}

    def generate(self, request: LLMRequest) -> LLMResponse:
        mensagens = ([{"role": "system", "content": request.system}] if request.system else []) + [{"role": "user", "content": request.prompt}]
        corpo: dict = {"model": self._modelo, "messages": mensagens, "max_tokens": request.max_tokens}
        if request.temperature is not None:
            corpo["temperature"] = request.temperature
        dados = self._post(self._url, {"Authorization": f"Bearer {self._chave}", "Content-Type": "application/json", **self._extras}, corpo)
        escolhas = dados.get("choices")
        if not isinstance(escolhas, list) or not escolhas or not isinstance(escolhas[0], dict):
            raise LLMFalhaDeProvedor(f"{self.id} devolveu uma resposta sem 'choices'.")
        escolha = escolhas[0]
        texto = self._texto_valido((escolha.get("message") or {}).get("content"))
        if escolha.get("finish_reason") == "length":
            raise LLMIndisponivel(f"{self.id}: a IA foi cortada antes de terminar a resposta (limite de tokens).")
        uso = dados.get("usage") or {}
        return LLMResponse(
            content=texto, model=str(dados.get("model") or self._modelo), input_tokens=int(uso.get("prompt_tokens") or 0),
            output_tokens=int(uso.get("completion_tokens") or 0), provider=self.id,
        )


def groq(*, chave: str, modelo: str, transport: httpx.BaseTransport | None = None) -> OpenAICompativel:
    return OpenAICompativel(id="groq", url="https://api.groq.com/openai/v1/chat/completions", chave=chave, modelo=modelo, transport=transport)


def openrouter(*, chave: str, modelo: str, transport: httpx.BaseTransport | None = None) -> OpenAICompativel:
    return OpenAICompativel(id="openrouter", url="https://openrouter.ai/api/v1/chat/completions", chave=chave, modelo=modelo, transport=transport)


class CloudflareWorkersAI(_ProvedorHttp):
    """REST `POST /accounts/{account_id}/ai/run/{modelo}` com Bearer token; resposta em `result.response`.

    O corpo usa `messages` (formato de chat dos modelos de texto do Workers AI). A página de início rápido consultada em
    2026-10-20 mostra só o campo `prompt`: o formato `messages` e o campo `usage` ficam **sem confirmação contra o serviço
    real** até o teste real; tokens ausentes na resposta são registrados como 0 (não estimados)."""

    id = "cloudflare"

    def __init__(self, *, account_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._account_id = account_id

    def generate(self, request: LLMRequest) -> LLMResponse:
        mensagens = ([{"role": "system", "content": request.system}] if request.system else []) + [{"role": "user", "content": request.prompt}]
        corpo: dict = {"messages": mensagens, "max_tokens": request.max_tokens}
        if request.temperature is not None:
            corpo["temperature"] = request.temperature
        url = f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}/ai/run/{self._modelo}"
        dados = self._post(url, {"Authorization": f"Bearer {self._chave}", "Content-Type": "application/json"}, corpo)
        if dados.get("success") is False:
            raise LLMFalhaDeProvedor("cloudflare: a API informou falha na execução.")
        resultado = dados.get("result") or {}
        texto = self._texto_valido(resultado.get("response") if isinstance(resultado, dict) else None)
        uso = (resultado.get("usage") or {}) if isinstance(resultado, dict) else {}
        return LLMResponse(
            content=texto, model=self._modelo, input_tokens=int(uso.get("prompt_tokens") or 0),
            output_tokens=int(uso.get("completion_tokens") or 0), provider=self.id,
        )


class GoogleGemini(_ProvedorHttp):
    """REST `POST /v1beta/models/{modelo}:generateContent` com a chave no cabeçalho `x-goog-api-key` (nunca na URL)."""

    id = "gemini"

    def generate(self, request: LLMRequest) -> LLMResponse:
        configuracao: dict = {"maxOutputTokens": request.max_tokens}
        if request.temperature is not None:
            configuracao["temperature"] = request.temperature
        corpo: dict = {"contents": [{"role": "user", "parts": [{"text": request.prompt}]}], "generationConfig": configuracao}
        if request.system:
            corpo["systemInstruction"] = {"parts": [{"text": request.system}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._modelo}:generateContent"
        dados = self._post(url, {"x-goog-api-key": self._chave, "Content-Type": "application/json"}, corpo)
        candidatos = dados.get("candidates")
        if not isinstance(candidatos, list) or not candidatos or not isinstance(candidatos[0], dict):
            # sem candidatos = prompt bloqueado por segurança ou resposta vazia: o provedor respondeu, não há texto
            raise LLMIndisponivel("gemini: a IA não retornou texto na resposta.")
        candidato = candidatos[0]
        partes = (candidato.get("content") or {}).get("parts") or []
        texto = self._texto_valido("".join(p.get("text", "") for p in partes if isinstance(p, dict)))
        if candidato.get("finishReason") == "MAX_TOKENS":
            raise LLMIndisponivel("gemini: a IA foi cortada antes de terminar a resposta (limite de tokens).")
        uso = dados.get("usageMetadata") or {}
        return LLMResponse(
            content=texto, model=str(dados.get("modelVersion") or self._modelo), input_tokens=int(uso.get("promptTokenCount") or 0),
            output_tokens=int(uso.get("candidatesTokenCount") or 0), provider=self.id,
        )
