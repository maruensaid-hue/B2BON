"""Universal AI Gateway (Fase 4, Master Prompt §52).

    MODULE → AI GATEWAY → MODEL ROUTER → PROVIDER → USAGE LEDGER

Único caminho de código para chamar um LLM (verificado por
`tests/unit/test_gateway_ia_unico_caminho.py`). Para cada chamada:

1. `ContextoIA` válido: tenant obrigatório; feature registrada
   (`registro.FEATURES`) — dá módulo, agente, classe de modelo e gatilho.
2. C0 nunca chama LLM.
3. Gatilho automático (webhook, bot de reunião, cron) respeita um teto por
   tenant/hora (`AI_LIMITE_AUTOMATICO_POR_HORA`).
4. Roteia o modelo pela classe e só manda `temperature` a quem aceita.
5. Feature que carrega conteúdo externo recebe a instrução de sistema
   anti-injeção (`prompt_seguro`).
6. Registra `RegistroUsoIa` — sucesso, falha ou bloqueio — numa sessão
   própria, independente da transação de quem chamou: um rollback do
   chamador não apaga o uso já incorrido.
"""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.contexts.intelligence import prompt_seguro, registro, roteador
from app.core.config import settings
from app.core.observability import correlation_id_atual
from app.core.rate_limit import LimitadorEmMemoria
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.registro_uso_ia import RegistroUsoIa
from app.services import llm_helpers
from app.services.errors import LimiteDeTaxaExcedido, RegraNegocioViolada

logger = logging.getLogger(__name__)

limitador_automatico = LimitadorEmMemoria()


@dataclass(frozen=True)
class ContextoIA:
    tenant_id: str
    feature: str
    usuario_id: int | None = None
    workflow: str | None = None
    entidade_tipo: str | None = None
    entidade_id: int | None = None
    gatilho: registro.Gatilho | None = None  # sobrescreve o da feature (ex.: API)


def _usuario_int(usuario_id) -> int | None:
    try:
        return int(usuario_id) if usuario_id is not None else None
    except (TypeError, ValueError):
        return None


def _registrar(db: Session, ctx: ContextoIA, feature: registro.Feature, gatilho: str, classe: str,
               modelo: str | None, resposta: LLMResponse | None, latencia_ms: int, status: str, erro: str | None) -> None:
    linha = RegistroUsoIa(
        tenant_id=ctx.tenant_id,
        agente=feature.agente,
        modulo=feature.modulo,
        feature=feature.nome,
        workflow=ctx.workflow,
        usuario_id=_usuario_int(ctx.usuario_id),
        provider=resposta.provider if resposta else "anthropic",
        classe_modelo=classe,
        gatilho=gatilho,
        model=resposta.model if resposta else modelo,
        tokens_entrada=resposta.input_tokens if resposta else 0,
        tokens_saida=resposta.output_tokens if resposta else 0,
        tokens_cache_leitura=resposta.cache_read_input_tokens if resposta else 0,
        tokens_cache_escrita=resposta.cache_creation_input_tokens if resposta else 0,
        latencia_ms=latencia_ms,
        entidade_tipo=ctx.entidade_tipo,
        entidade_id=ctx.entidade_id,
        status=status,
        erro=(erro or None) and erro[:500],
        correlation_id=correlation_id_atual(),
    )
    sessao = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    try:
        sessao.add(linha)
        sessao.commit()
    except Exception:  # noqa: BLE001
        sessao.rollback()
        # Falha de ledger é incidente de FinOps, não silêncio (Fase 5 reconcilia).
        logger.error("LEDGER_IA_FALHOU tenant=%s feature=%s status=%s", ctx.tenant_id, feature.nome, status, exc_info=True)
    finally:
        sessao.close()


def gerar(db: Session, llm: LLMProvider, ctx: ContextoIA, requisicao: LLMRequest) -> LLMResponse:
    if not ctx.tenant_id:
        raise ValueError("ContextoIA sem tenant_id: chamada de IA recusada.")
    feature = registro.obter_feature(ctx.feature)
    gatilho = (ctx.gatilho or feature.gatilho).value
    modelo = roteador.modelo_para(feature.classe)

    if gatilho == registro.Gatilho.AUTOMATICO.value:
        try:
            limitador_automatico.checar(f"ia-auto:{ctx.tenant_id}", settings.ai_limite_automatico_por_hora, 3600)
        except LimiteDeTaxaExcedido as erro:
            _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None, 0, "bloqueado", "limite automático por hora")
            raise RegraNegocioViolada("Limite de uso automático de IA atingido nesta hora.") from erro

    requisicao = requisicao.model_copy(
        update={
            "model": modelo.id,
            "temperature": requisicao.temperature if modelo.aceita_amostragem else None,
            "system": prompt_seguro.com_instrucao_de_sistema(requisicao.system) if feature.conteudo_externo else requisicao.system,
        }
    )

    inicio = time.monotonic()
    try:
        resposta = llm_helpers.gerar(llm, requisicao)
    except RegraNegocioViolada as erro:
        _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None,
                   int((time.monotonic() - inicio) * 1000), "falha", str(erro.__cause__ or erro))
        raise
    _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, resposta,
               int((time.monotonic() - inicio) * 1000), "sucesso", None)
    return resposta
