"""Registro dos provedores adicionais de IA, regras de habilitação e fallback controlado.

Princípios (Master Prompt V5.1, pendência 1):

* **Nada muda por padrão**: sem `AI_PROVEDORES_FALLBACK`, `construir_provedor` devolve o `ClaudeProvider` puro, exatamente como antes.
* **Nenhuma chamada silenciosa**: um provedor só entra na cadeia se estiver na lista, tiver credencial e modelo, estiver marcado como
  aprovado para dados reais, passar na trava de custo e não ter estourado o teto diário. Qualquer outra situação aparece em
  `status_provedores()` com o motivo do bloqueio e o adapter nem é construído.
* **Sem cobrança inesperada**: provedor de plano pago só com `AI_FALLBACK_PERMITE_PAGO=true`; OpenRouter gratuito exige modelo `:free`;
  há teto diário de chamadas por provedor (contado no ledger de uso de IA); falha acima do teto ou do disjuntor apenas pula o provedor.
* **Só falha do provedor aciona o fallback**: resposta vazia/cortada (`LLMIndisponivel`) é do conteúdo e não troca de fornecedor.
* O fallback recebe o mesmo prompt (com dados do cliente): por isso a aprovação de privacidade é obrigatória e explícita.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.disjuntor import Disjuntor
from app.llm import provedores
from app.llm.base import LLMFalhaDeProvedor, LLMProvider
from app.llm.claude_provider import ClaudeProvider
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.registro_uso_ia import RegistroUsoIa

logger = logging.getLogger(__name__)

VERIFICADO_EM = "2026-10-20"
_PLANOS_VALIDOS = ("gratuito", "pago")


@dataclass(frozen=True)
class Definicao:
    id: str
    nome: str
    variaveis: tuple[str, ...]
    documentacao: str
    limites: str
    retencao: str
    construir: Callable[[httpx.BaseTransport | None], LLMProvider]
    credencial: Callable[[], bool]
    modelo: Callable[[], str]
    plano: Callable[[], str]
    aprovado: Callable[[], bool]


DEFINICOES: tuple[Definicao, ...] = (
    Definicao(
        id="cloudflare", nome="Cloudflare Workers AI",
        variaveis=("CLOUDFLARE_AI_ACCOUNT_ID", "CLOUDFLARE_AI_API_TOKEN", "CLOUDFLARE_AI_MODELO", "CLOUDFLARE_AI_PLANO", "CLOUDFLARE_AI_APROVADO_DADOS_REAIS"),
        documentacao="https://developers.cloudflare.com/workers-ai/platform/pricing/",
        limites="Plano Free: 10.000 Neurons/dia sem custo; acima disso as chamadas falham com erro (sem cobrança no Free). Plano Workers Paid: US$ 0,011 por 1.000 Neurons além da franquia diária.",
        retencao="Cloudflare declara que não usa o conteúdo processado para treinar modelos e não o retém após a inferência padrão; recursos com estado (AI Gateway com log/cache, R2, KV etc.) seguem a retenção do próprio recurso. Metadados (tokens/neurons, latência) são retidos.",
        construir=lambda t: provedores.CloudflareWorkersAI(account_id=settings.cloudflare_ai_account_id, chave=settings.cloudflare_ai_api_token, modelo=settings.cloudflare_ai_modelo, transport=t),
        credencial=lambda: bool(settings.cloudflare_ai_account_id and settings.cloudflare_ai_api_token),
        modelo=lambda: settings.cloudflare_ai_modelo, plano=lambda: settings.cloudflare_ai_plano, aprovado=lambda: settings.cloudflare_ai_aprovado_dados_reais,
    ),
    Definicao(
        id="groq", nome="GroqCloud",
        variaveis=("GROQ_API_KEY", "GROQ_MODELO", "GROQ_PLANO", "GROQ_APROVADO_DADOS_REAIS"),
        documentacao="https://console.groq.com/docs/rate-limits",
        limites="Limites por modelo e por plano (a documentação consultada lista só o plano Developer: ex.: 30 RPM, 1K RPD no gpt-oss-120b); ao exceder devolve 429. Não está documentado se exceder o plano gratuito gera cobrança.",
        retencao="Por padrão não retém entradas/saídas da inferência; pode registrar temporariamente por até 30 dias para depuração/abuso. Zero Data Retention (ZDR) disponível nos Data Controls da organização. A página consultada não afirma nada sobre treinamento.",
        construir=lambda t: provedores.groq(chave=settings.groq_api_key, modelo=settings.groq_modelo, transport=t),
        credencial=lambda: bool(settings.groq_api_key), modelo=lambda: settings.groq_modelo, plano=lambda: settings.groq_plano,
        aprovado=lambda: settings.groq_aprovado_dados_reais,
    ),
    Definicao(
        id="openrouter", nome="OpenRouter",
        variaveis=("OPENROUTER_API_KEY", "OPENROUTER_MODELO", "OPENROUTER_PLANO", "OPENROUTER_APROVADO_DADOS_REAIS"),
        documentacao="https://openrouter.ai/docs/faq",
        limites="Modelos gratuitos (id terminado em ':free'): 50 requisições/dia sem créditos comprados; 1.000/dia com ao menos 10 créditos. A própria documentação diz que modelos gratuitos têm limites baixos e em geral não servem para produção; disponibilidade não é garantida.",
        retencao="Não registra prompts/respostas por padrão (só metadados); não roteia para provedores que registram, exceto se a configuração de privacidade permitir. A FAQ não diz se isso muda para modelos gratuitos: validar nas configurações de privacidade da conta.",
        construir=lambda t: provedores.openrouter(chave=settings.openrouter_api_key, modelo=settings.openrouter_modelo, transport=t),
        credencial=lambda: bool(settings.openrouter_api_key), modelo=lambda: settings.openrouter_modelo, plano=lambda: settings.openrouter_plano,
        aprovado=lambda: settings.openrouter_aprovado_dados_reais,
    ),
    Definicao(
        id="gemini", nome="Google Gemini API",
        variaveis=("GEMINI_API_KEY", "GEMINI_MODELO", "GEMINI_PLANO", "GEMINI_APROVADO_DADOS_REAIS"),
        documentacao="https://ai.google.dev/gemini-api/terms",
        limites="Limites por projeto, não garantidos e sujeitos a mudança; no nível gratuito não há limite de gasto e a documentação não diz se exceder gera cobrança automática.",
        retencao="Serviços não pagos: Google usa prompts e respostas para melhorar produtos e revisores humanos podem lê-los; os termos pedem para NÃO enviar dados pessoais/confidenciais. Serviços pagos: não usa para melhorar produtos, registra por tempo limitado (abuso/obrigação legal). No EEE/Suíça/Reino Unido os termos de serviços pagos valem para todos.",
        construir=lambda t: provedores.GoogleGemini(chave=settings.gemini_api_key, modelo=settings.gemini_modelo, transport=t),
        credencial=lambda: bool(settings.gemini_api_key), modelo=lambda: settings.gemini_modelo, plano=lambda: settings.gemini_plano,
        aprovado=lambda: settings.gemini_aprovado_dados_reais,
    ),
)
_POR_ID = {d.id: d for d in DEFINICOES}


def _listados() -> list[str]:
    return [p.strip().lower() for p in settings.ai_provedores_fallback.split(",") if p.strip()]


def avaliar(definicao: Definicao) -> tuple[str, list[str]]:
    """(estado, bloqueios): nao_configurado | configurado | bloqueado | ativo."""
    configurado = definicao.credencial() and bool(definicao.modelo().strip())
    if not configurado:
        return "nao_configurado", []
    if definicao.id not in _listados():
        return "configurado", []
    bloqueios: list[str] = []
    plano = definicao.plano().strip().lower()
    if plano not in _PLANOS_VALIDOS:
        bloqueios.append("plano_invalido: use 'gratuito' ou 'pago'")
    elif plano == "pago" and not settings.ai_fallback_permite_pago:
        bloqueios.append("plano_pago_nao_permitido: defina AI_FALLBACK_PERMITE_PAGO=true com autorização de custo")
    if not definicao.aprovado():
        bloqueios.append("sem_aprovacao_de_privacidade: nenhum dado real é enviado antes da aprovação explícita")
    if definicao.id == "openrouter" and plano == "gratuito" and not definicao.modelo().strip().endswith(":free"):
        bloqueios.append("modelo_nao_gratuito: com plano gratuito o modelo precisa terminar em ':free'")
    return ("bloqueado" if bloqueios else "ativo"), bloqueios


def status_provedores() -> list[dict]:
    """Estado de cada provedor para a tela/relatório de operação. Nunca devolve credenciais."""
    anthropic = {
        "id": "anthropic", "nome": "Anthropic (Claude) — provedor padrão", "adapter_implementado": True, "teste_simulado": True,
        "teste_real": "aprovado (em produção)", "estado": "ativo" if settings.anthropic_api_key else "nao_configurado", "bloqueios": [],
        "aprovado_dados_reais": True, "plano_declarado": "pago", "variaveis": ["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"],
    }
    resultado = [anthropic]
    for d in DEFINICOES:
        estado, bloqueios = avaliar(d)
        resultado.append({
            "id": d.id, "nome": d.nome, "adapter_implementado": True, "teste_simulado": True, "teste_real": "nao_realizado",
            "estado": estado, "bloqueios": bloqueios, "habilitado_na_lista": d.id in _listados(), "aprovado_dados_reais": d.aprovado(),
            "plano_declarado": d.plano(), "variaveis": list(d.variaveis), "documentacao": d.documentacao,
            "verificado_em": VERIFICADO_EM, "limites_documentados": d.limites, "retencao_documentada": d.retencao,
        })
    return resultado


def contar_sucessos_hoje(db: Session, provider_id: str) -> int:
    inicio = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return db.query(RegistroUsoIa).filter(
        RegistroUsoIa.provider == provider_id, RegistroUsoIa.status == "sucesso", RegistroUsoIa.criado_em >= inicio,
    ).count()


_DISJUNTORES: dict[str, Disjuntor] = {}


def _disjuntor(provider_id: str) -> Disjuntor:
    return _DISJUNTORES.setdefault(provider_id, Disjuntor())


def reiniciar_disjuntores() -> None:
    _DISJUNTORES.clear()


class ProvedorComFallback(LLMProvider):
    """Tenta o provedor principal; se ELE falhar (rede, timeout, 429, 5xx, credencial), tenta os adicionais na ordem configurada."""

    def __init__(self, primario: LLMProvider, adicionais: list[tuple[str, LLMProvider]], contar_hoje: Callable[[str], int],
                 limite_diario: int) -> None:
        self._primario, self._adicionais = primario, adicionais
        self._contar_hoje, self._limite = contar_hoje, limite_diario

    def generate(self, request: LLMRequest) -> LLMResponse:
        ultimo: LLMFalhaDeProvedor | None = None
        primario = _disjuntor("primario")
        if primario.permite():
            try:
                resposta = self._primario.generate(request)
                primario.sucesso()
                return resposta
            except LLMFalhaDeProvedor as erro:
                primario.falha()
                ultimo = erro
                logger.warning("PROVEDOR_PRINCIPAL_FALHOU motivo=%s tentando_fallback=%s", erro, bool(self._adicionais))
        else:
            ultimo = LLMFalhaDeProvedor("Provedor principal temporariamente indisponível (disjuntor aberto).")
        for provider_id, provedor in self._adicionais:
            circuito = _disjuntor(provider_id)
            if not circuito.permite():
                continue
            if self._contar_hoje(provider_id) >= self._limite:
                logger.warning("FALLBACK_TETO_DIARIO provider=%s limite=%s", provider_id, self._limite)
                continue
            try:
                # o id de modelo do request é da Anthropic: cada adapter usa o modelo configurado para ele
                resposta = provedor.generate(request.model_copy(update={"model": None}))
                circuito.sucesso()
                logger.warning("FALLBACK_USADO provider=%s", provider_id)
                return resposta
            except LLMFalhaDeProvedor as erro:
                circuito.falha()
                ultimo = erro
        raise ultimo or LLMFalhaDeProvedor("Nenhum provedor de IA disponível no momento.")


def construir_provedor(db: Session, transport: httpx.BaseTransport | None = None) -> LLMProvider:
    """Provedor usado pelo gateway: a Anthropic pura, ou ela com fallback quando há provedores ativos (e só então)."""
    primario = ClaudeProvider()
    ativos = [d for d in DEFINICOES if avaliar(d)[0] == "ativo"]
    if not ativos:
        return primario
    ordem = {pid: i for i, pid in enumerate(_listados())}
    adicionais = [(d.id, d.construir(transport)) for d in sorted(ativos, key=lambda d: ordem[d.id])]
    return ProvedorComFallback(primario, adicionais, lambda pid: contar_sucessos_hoje(db, pid), settings.ai_fallback_limite_diario)
