import logging
import time

from sqlalchemy.orm import Session

from app.llm.base import LLMIndisponivel, LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.registro_uso_ia import RegistroUsoIa
from app.services.errors import RegraNegocioViolada

logger = logging.getLogger(__name__)


def gerar(llm: LLMProvider, request: LLMRequest) -> LLMResponse:
    """Chama o LLM traduzindo falha de infraestrutura (chave ausente, rede,
    limite de taxa) em erro de negócio claro — sem isto, qualquer problema
    na chamada à IA virava um 500 genérico sem explicação para quem usa a
    tela (bug real: geração de cadência "não funcionava" sem nenhuma pista
    do porquê)."""
    try:
        return llm.generate(request)
    except LLMIndisponivel as erro:
        raise RegraNegocioViolada(
            f"Não foi possível gerar o texto com IA no momento ({erro}). "
            "Tente novamente em instantes; se persistir, avise o administrador."
        ) from erro


def gerar_e_registrar(
    db: Session,
    tenant_id: str,
    agente: str,
    llm: LLMProvider,
    request: LLMRequest,
    *,
    entidade_tipo: str | None = None,
    entidade_id: int | None = None,
) -> LLMResponse:
    """Mesmo `gerar` acima, mas também registra tokens/latência/modelo em
    `RegistroUsoIa` (master prompt §85 Cost Governance + §73 AI Audit,
    Fases 7C/0.5-C) — só os agentes da Fase 6 migram pra esta função
    (decisão de escopo; os ~15 call sites mais antigos de `gerar`
    continuam como estão). `entidade_tipo`/`entidade_id` são opcionais
    e só preenchidos quando a entidade gerada já existe no momento da
    chamada — `None` aqui é dado real (ex.: teste interno do Corporate
    AI Agent nunca persiste nada), não uma omissão. Só grava quando a
    chamada teve sucesso (nunca inventa um registro pra uma chamada
    que falhou) e falha ao PERSISTIR o registro nunca derruba a
    resposta real da IA — é best-effort, puramente observação."""
    inicio = time.monotonic()
    resposta = gerar(llm, request)
    latencia_ms = int((time.monotonic() - inicio) * 1000)

    try:
        db.add(
            RegistroUsoIa(
                tenant_id=tenant_id,
                agente=agente,
                tokens_entrada=resposta.input_tokens,
                tokens_saida=resposta.output_tokens,
                latencia_ms=latencia_ms,
                model=resposta.model,
                entidade_tipo=entidade_tipo,
                entidade_id=entidade_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Falha ao registrar uso de IA (tenant=%s, agente=%s) — resposta seguiu normalmente.", tenant_id, agente)

    return resposta
