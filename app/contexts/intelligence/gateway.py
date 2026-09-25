"""Universal AI Gateway (Fase 4, Master Prompt §52; AI Credits na Fase 15).

    MODULE → AI GATEWAY → ENTITLEMENT/BUDGET CHECK → CREDIT CHECK (reserva)
           → AI ROUTER → COST GUARD → CACHE CHECK → MODEL → USAGE METER
           → COST ATTRIBUTION → CREDIT LEDGER (liquidação) → RESULT

Único caminho de código para chamar um LLM (verificado por
`tests/unit/test_gateway_ia_unico_caminho.py`). Para cada chamada:

1. `ContextoIA` válido: tenant obrigatório; feature registrada
   (`registro.FEATURES`) — dá módulo, agente, classe, gatilho e o
   workload do catálogo de AI Credits (`registro.WORKLOAD_POR_FEATURE`).
2. C0 nunca chama LLM.
3. Gatilho automático respeita um teto por tenant/hora.
4. Budgets antigos (USD/chamadas) e o budget guard em créditos são
   checados antes do provedor.
5. Crédito: sem `execucao_id`, a chamada abre uma execução implícita
   (reserva o peso do workload); com `execucao_id`, soma custo numa
   execução explícita (operação longa em várias chamadas, cobrada uma vez).
6. Roteia o modelo pela classe; o cost guard só troca para classe mais
   barata se o workload permitir (`classe_minima`) — nunca abaixo dela.
7. Cache de resposta por tenant para features cacheáveis: o hit não
   chama o provedor e o crédito continua cobrado (economia = margem).
8. Registra `RegistroUsoIa` (sucesso, falha, bloqueio) com custo e a
   execução, numa sessão própria; liquida a execução implícita. Falha
   do provedor libera a reserva: nada é cobrado sem resultado.
"""

import hashlib
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.contexts.finops import contract as finops
from app.contexts.intelligence import prompt_seguro, registro, roteador
from app.core.config import settings
from app.core.observability import correlation_id_atual
from app.core.rate_limit import LimitadorEmMemoria
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse
from app.models.creditos_ia import CacheRespostaIa
from app.models.registro_uso_ia import RegistroUsoIa
from app.services import llm_helpers
from app.services.errors import LimiteDeTaxaExcedido, NaoEncontrado, RegraNegocioViolada

logger = logging.getLogger(__name__)

limitador_automatico = LimitadorEmMemoria()
_ORDEM_CLASSES = ("C1", "C2", "C3")


@dataclass(frozen=True)
class ContextoIA:
    tenant_id: str
    feature: str
    usuario_id: int | None = None
    workflow: str | None = None
    entidade_tipo: str | None = None
    entidade_id: int | None = None
    gatilho: registro.Gatilho | None = None  # sobrescreve o da feature (ex.: API)
    # Fase 15 — AI Credits
    execucao_id: str | None = None  # execução explícita (operação em várias chamadas)
    idempotency_key: str | None = None  # retry técnico não cobra duas vezes
    confirmado: bool = False  # usuário viu a estimativa e confirmou


@dataclass(frozen=True)
class _Medicao:
    execucao_id: str | None
    workload: str | None
    catalogo_versao: str | None
    creditos: Decimal | None
    cache_hit: bool = False
    economia_cache_usd: Decimal | None = None
    decisao_roteamento: str | None = None


def _usuario_int(usuario_id) -> int | None:
    try:
        return int(usuario_id) if usuario_id is not None else None
    except (TypeError, ValueError):
        return None


def _registrar(db: Session, ctx: ContextoIA, feature: registro.Feature, gatilho: str, classe: str,
               modelo: str | None, resposta: LLMResponse | None, latencia_ms: int, status: str, erro: str | None,
               medicao: _Medicao | None = None) -> None:
    medicao = medicao or _Medicao(None, None, None, None)
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
        execucao_id=medicao.execucao_id,
        workload_codigo=medicao.workload,
        catalogo_versao=medicao.catalogo_versao,
        creditos_consumidos=medicao.creditos,
        cache_hit=medicao.cache_hit,
        decisao_roteamento=medicao.decisao_roteamento,
    )
    sessao = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    try:
        # Evento de uso, custo e agregado da execução na MESMA transação:
        # ou entram juntos, ou nenhum.
        if resposta is not None and not medicao.cache_hit:
            custo, preco_id, economia = finops.custear(
                sessao, resposta.model, resposta.input_tokens, resposta.output_tokens,
                resposta.cache_creation_input_tokens, resposta.cache_read_input_tokens, resposta.provider,
            )
            linha.custo_usd, linha.preco_id, linha.economia_cache_usd = custo, preco_id, economia
        elif medicao.cache_hit:
            linha.custo_usd, linha.economia_cache_usd = Decimal(0), medicao.economia_cache_usd
        sessao.add(linha)
        sessao.flush()
        if medicao.execucao_id and resposta is not None:
            finops.execucoes.registrar_chamada(sessao, medicao.execucao_id, linha.custo_usd, linha.economia_cache_usd, medicao.cache_hit)
        sessao.commit()
    except Exception:  # noqa: BLE001
        sessao.rollback()
        # Falha de ledger é incidente de FinOps, não silêncio (reconciliação).
        logger.error("LEDGER_IA_FALHOU tenant=%s feature=%s status=%s", ctx.tenant_id, feature.nome, status, exc_info=True)
    finally:
        sessao.close()


def _estimar_custo_usd(db: Session, modelo: str, requisicao: LLMRequest) -> Decimal | None:
    """Estimativa pessimista: ~4 caracteres por token de entrada e o teto de saída."""
    entrada = (len(requisicao.prompt) + len(requisicao.system or "")) // 4
    preco = finops.precos.obter_preco(db, modelo)
    return finops.precos.calcular_custo(preco, entrada, requisicao.max_tokens) if preco else None


def _cost_guard(db: Session, workload, classe: roteador.ClasseModelo, requisicao: LLMRequest) -> tuple[roteador.ModeloRoteado, str | None]:
    """Custo estimado acima do teto do workload: tenta classe mais barata só
    até a `classe_minima` do workload; se não houver, segue e registra
    (o teto é guarda interna de margem, não pode derrubar qualidade)."""
    modelo = roteador.modelo_para(classe)
    teto = Decimal(str(workload.custo_max_usd)) if workload is not None and workload.custo_max_usd is not None else None
    if teto is None:
        return modelo, None
    estimado = _estimar_custo_usd(db, modelo.id, requisicao)
    if estimado is None or estimado <= teto:
        return modelo, None
    minima = ((workload.politica_modelo or {}).get("classe_minima") or classe.value)
    for candidata in _ORDEM_CLASSES[_ORDEM_CLASSES.index(minima):_ORDEM_CLASSES.index(classe.value)]:
        alternativo = roteador.modelo_para(roteador.ClasseModelo(candidata))
        custo_alt = _estimar_custo_usd(db, alternativo.id, requisicao)
        if custo_alt is not None and custo_alt <= teto:
            return alternativo, f"cost_guard:{classe.value}->{candidata}"
    logger.warning("CUSTO_ACIMA_DO_TETO workload=%s estimado_usd=%s teto_usd=%s", workload.codigo, estimado, teto)
    return modelo, f"cost_guard:acima_do_teto({estimado}>{teto})"


def _chave_cache(ctx: ContextoIA, modelo: str, requisicao: LLMRequest) -> str:
    conteudo = "\x1f".join([ctx.tenant_id, ctx.feature, modelo, requisicao.system or "", requisicao.prompt])
    return hashlib.sha256(conteudo.encode()).hexdigest()


def _cache_ler(db: Session, chave: str, tenant_id: str) -> CacheRespostaIa | None:
    item = db.get(CacheRespostaIa, chave)
    if item is None or item.tenant_id != tenant_id or item.expira_em <= finops.carteira.agora_utc():
        return None
    return item


def _cache_gravar(db: Session, chave: str, ctx: ContextoIA, resposta: LLMResponse) -> None:
    sessao = sessionmaker(bind=db.get_bind())()
    try:
        custo, _, _ = finops.custear(sessao, resposta.model, resposta.input_tokens, resposta.output_tokens, 0, 0, resposta.provider)
        existente = sessao.get(CacheRespostaIa, chave)
        if existente is not None:
            sessao.delete(existente)
            sessao.flush()
        sessao.add(CacheRespostaIa(
            chave=chave, tenant_id=ctx.tenant_id, feature=ctx.feature, modelo=resposta.model, conteudo=resposta.content,
            custo_original_usd=custo, tokens_entrada=resposta.input_tokens, tokens_saida=resposta.output_tokens, hits=0,
            expira_em=finops.carteira.agora_utc() + timedelta(hours=finops.comercial.horas_cache_resposta()),
        ))
        sessao.commit()
    except Exception:  # noqa: BLE001 — cache é otimização, nunca derruba a chamada
        sessao.rollback()
        logger.warning("CACHE_IA_FALHOU feature=%s", ctx.feature, exc_info=True)
    finally:
        sessao.close()


def _execucao(db: Session, ctx: ContextoIA, feature: registro.Feature, gatilho: str):
    """(execucao, implicita). Levanta erro de crédito/orçamento antes do provedor."""
    if ctx.execucao_id:
        execucao = finops.execucoes.obter(db, ctx.tenant_id, ctx.execucao_id)
        return execucao, False
    execucao = finops.execucoes.abrir(
        db, ctx.tenant_id, registro.workload_da_feature(feature.nome), feature=feature.nome, agente=feature.agente,
        gatilho=gatilho, usuario_id=_usuario_int(ctx.usuario_id), idempotency_key=ctx.idempotency_key,
        confirmado=ctx.confirmado, modulo=feature.modulo,
    )
    return execucao, True


def gerar(db: Session, llm: LLMProvider, ctx: ContextoIA, requisicao: LLMRequest) -> LLMResponse:
    if not ctx.tenant_id:
        raise ValueError("ContextoIA sem tenant_id: chamada de IA recusada.")
    feature = registro.obter_feature(ctx.feature)
    gatilho = (ctx.gatilho or feature.gatilho).value
    classe = feature.classe
    modelo = roteador.modelo_para(classe)

    if gatilho == registro.Gatilho.AUTOMATICO.value:
        try:
            limitador_automatico.checar(f"ia-auto:{ctx.tenant_id}", settings.ai_limite_automatico_por_hora, 3600)
        except LimiteDeTaxaExcedido as erro:
            _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None, 0, "bloqueado", "limite automático por hora")
            raise RegraNegocioViolada("Limite de uso automático de IA atingido nesta hora.") from erro

    motivo = finops.orcamentos.motivo_de_bloqueio(db, ctx.tenant_id, feature.modulo, feature.nome)
    if motivo is not None:
        _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None, 0, "bloqueado", motivo)
        raise RegraNegocioViolada(f"IA indisponível: {motivo}.")

    try:
        execucao, implicita = _execucao(db, ctx, feature, gatilho)
    except NaoEncontrado:
        raise
    except RegraNegocioViolada as erro:  # créditos, confirmação, orçamento, concorrência
        _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None, 0, "bloqueado", str(erro))
        raise
    except LimiteDeTaxaExcedido as erro:
        _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None, 0, "bloqueado", str(erro))
        raise
    workload = finops.catalogos.obter_workload(db, execucao.workload_codigo, finops.catalogos.obter_catalogo(db, execucao.catalogo_versao))

    modelo, decisao = _cost_guard(db, workload, classe, requisicao)
    medicao = _Medicao(execucao.id, execucao.workload_codigo, execucao.catalogo_versao,
                       Decimal(str(execucao.creditos_estimados)) if implicita else None, decisao_roteamento=decisao)
    requisicao = requisicao.model_copy(
        update={
            "model": modelo.id,
            "temperature": requisicao.temperature if modelo.aceita_amostragem else None,
            "system": prompt_seguro.com_instrucao_de_sistema(requisicao.system) if feature.conteudo_externo else requisicao.system,
        }
    )

    chave = _chave_cache(ctx, modelo.id, requisicao) if feature.nome in registro.FEATURES_CACHEAVEIS else None
    if chave is not None:
        cache = _cache_ler(db, chave, ctx.tenant_id)
        if cache is not None:
            resposta = LLMResponse(content=cache.conteudo, model=cache.modelo or modelo.id, input_tokens=0, output_tokens=0, provider="cache")
            economia = finops.custo_evitado(db, cache.modelo, cache.tokens_entrada, cache.tokens_saida)
            _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, resposta, 0, "sucesso", None,
                       replace(medicao, cache_hit=True, economia_cache_usd=economia))
            if implicita:
                finops.execucoes.liquidar(db, execucao.id)
            return resposta

    inicio = time.monotonic()
    try:
        resposta = llm_helpers.gerar(llm, requisicao)
    except Exception as erro:  # falha do provedor ou do sistema: o cliente não paga
        _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, None,
                   int((time.monotonic() - inicio) * 1000), "falha", str(erro.__cause__ or erro), medicao)
        if implicita:
            finops.execucoes.liberar(db, execucao.id, f"falha do provedor: {type(erro).__name__}")
        raise
    _registrar(db, ctx, feature, gatilho, modelo.classe.value, modelo.id, resposta,
               int((time.monotonic() - inicio) * 1000), "sucesso", None, medicao)
    if implicita:
        finops.execucoes.liquidar(db, execucao.id)
    if chave is not None:
        _cache_gravar(db, chave, ctx, resposta)
    return resposta


@contextmanager
def execucao(db: Session, ctx: ContextoIA, parametros: dict | None = None, confirmado: bool = False) -> Iterator[ContextoIA]:
    """Operação longa (várias chamadas) cobrada uma vez: estima pelo workload
    da feature com os `parametros` (páginas, documentos), reserva, e devolve
    o `ContextoIA` com `execucao_id` para as chamadas do bloco. Exceção no
    bloco = reserva liberada."""
    feature = registro.obter_feature(ctx.feature)
    gatilho = (ctx.gatilho or feature.gatilho).value
    with finops.execucoes.executar(
        db, ctx.tenant_id, registro.workload_da_feature(feature.nome), feature=feature.nome, agente=feature.agente, gatilho=gatilho,
        usuario_id=_usuario_int(ctx.usuario_id), parametros=parametros, idempotency_key=ctx.idempotency_key,
        confirmado=confirmado or ctx.confirmado, modulo=feature.modulo,
    ) as aberta:
        yield replace(ctx, execucao_id=aberta.id)


def estimar(db: Session, feature_nome: str, parametros: dict | None = None) -> dict:
    return finops.execucoes.estimar(db, registro.workload_da_feature(registro.obter_feature(feature_nome).nome), parametros)
