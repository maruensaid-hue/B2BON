"""Execuções de workload de IA (Fase 15): ESTIMATE → RESERVE → EXECUTE →
SETTLE → RELEASE, com idempotência e estorno.

- Toda chamada ao modelo pertence a uma execução. O gateway abre uma
  execução implícita por chamada; operações longas (edital em blocos,
  documento de 200 páginas) abrem uma explícita e as chamadas se
  penduram nela — a cobrança é UMA por operação, não por bloco.
- Idempotência por `(tenant, idempotency_key)`: retry técnico devolve a
  mesma execução; uma execução liquidada nunca é cobrada de novo.
- A reserva trava a carteira do tenant: duas operações simultâneas não
  reservam o mesmo saldo. Sem saldo, só passa com excedente aprovado
  (Enterprise) ou no modo MEASURE.
- Falha sem resultado utilizável libera a reserva (CREDIT_RELEASED); se
  já liquidada, estorna (CREDIT_REFUNDED).

Cada operação roda em sessão própria (como o ledger do gateway), para
não misturar a trava da carteira com a transação de negócio do chamador.
"""

import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.contexts.finops import carteira, catalogos, comercial, limites
from app.contexts.finops.comercial import Evento
from app.models.creditos_ia import ExecucaoIa
from app.services.errors import ConfirmacaoNecessaria, CreditosInsuficientes, LimiteDeTaxaExcedido, NaoEncontrado

logger = logging.getLogger("b2bon.creditos")
ZERO = Decimal(0)


def _sessao(db: Session) -> Session:
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)()


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def obter(db: Session, tenant_id: str, execucao_id: str) -> ExecucaoIa:
    execucao = db.get(ExecucaoIa, execucao_id)
    if execucao is None or execucao.tenant_id != tenant_id:
        raise NaoEncontrado(f"Execução {execucao_id} não encontrada.")
    return execucao


def estimar(db: Session, workload_codigo: str, parametros: dict | None = None) -> dict:
    catalogo = catalogos.catalogo_ativo(db)
    workload = catalogos.obter_workload(db, workload_codigo, catalogo)
    estimativa = catalogos.estimar(workload, catalogo.versao, parametros)
    return {
        "workload": workload.codigo, "nome": workload.nome, "catalogo_versao": catalogo.versao, "classe": workload.classe,
        "creditos_estimados": float(estimativa.creditos), "minimo": float(estimativa.minimo) if estimativa.minimo is not None else None,
        "maximo": float(estimativa.maximo) if estimativa.maximo is not None else None, "variavel": estimativa.variavel,
        "detalhe": estimativa.detalhe,
        "requer_confirmacao": bool(estimativa.creditos > 0 and (workload.requer_aprovacao or estimativa.creditos >= comercial.limiar_confirmacao())),
        "mensagem": f"Consumo estimado: aproximadamente {int(estimativa.creditos)} AI Credits.",
    }


def abrir(db: Session, tenant_id: str, workload_codigo: str, *, feature: str | None = None, agente: str | None = None,
          gatilho: str | None = None, usuario_id: int | None = None, parametros: dict | None = None,
          idempotency_key: str | None = None, confirmado: bool = False, modulo: str | None = None) -> ExecucaoIa:
    inicio = time.monotonic()
    chave = idempotency_key or uuid.uuid4().hex
    sessao = _sessao(db)
    try:
        existente = sessao.query(ExecucaoIa).filter_by(tenant_id=tenant_id, idempotency_key=chave).one_or_none()
        if existente is not None:
            return existente
        catalogo = catalogos.catalogo_ativo(sessao)
        workload = catalogos.obter_workload(sessao, workload_codigo, catalogo)
        estimativa = catalogos.estimar(workload, catalogo.versao, parametros)
        creditos = estimativa.creditos

        carteira.preparar(sessao, tenant_id)
        abertas = sessao.query(ExecucaoIa).filter_by(tenant_id=tenant_id, status="RESERVADA").count()
        if abertas >= comercial.max_reservas_abertas():
            logger.warning("CREDITOS_CONCORRENCIA tenant=%s abertas=%s", tenant_id, abertas)
            raise LimiteDeTaxaExcedido("Muitas operações de IA em andamento ao mesmo tempo. Aguarde e tente de novo.")
        if creditos > 0 and (workload.requer_aprovacao or creditos >= comercial.limiar_confirmacao()) and not confirmado:
            raise ConfirmacaoNecessaria(f"Consumo estimado: aproximadamente {int(creditos)} AI Credits.",
                                        estimar(sessao, workload_codigo, parametros))
        limites.verificar_orcamento(sessao, tenant_id, creditos, modulo=modulo or workload.modulo, agente=agente,
                                    usuario_id=usuario_id, gatilho=gatilho)

        disponivel = carteira.disponivel(sessao, tenant_id)
        if creditos > disponivel and not _pode_exceder(sessao, tenant_id, creditos - disponivel):
            raise CreditosInsuficientes(
                "Créditos de IA insuficientes para esta operação.",
                {"creditos_necessarios": float(creditos), "creditos_disponiveis": float(max(disponivel, ZERO)),
                 "acao": "Compre um pacote de AI Credits em Assinatura → AI Credits."},
            )
        reserva = min(creditos, max(disponivel, ZERO))
        execucao = ExecucaoIa(
            id=uuid.uuid4().hex, tenant_id=tenant_id, idempotency_key=chave, workload_codigo=workload.codigo,
            catalogo_versao=catalogo.versao, classe=workload.classe, modulo=modulo or workload.modulo, feature=feature, agente=agente,
            gatilho=gatilho, usuario_id=usuario_id, plano_id=carteira.plano_id(sessao, tenant_id), parametros=parametros,
            status="RESERVADA", creditos_estimados=creditos, creditos_reservados=reserva,
        )
        sessao.add(execucao)
        sessao.flush()
        if reserva > 0:
            carteira.movimentar(sessao, tenant_id, Evento.RESERVED, -reserva, execucao=execucao, descricao=workload.codigo)
        sessao.commit()
        logger.info("CREDITOS_RESERVA tenant=%s workload=%s creditos=%s latencia_ms=%s", tenant_id, workload.codigo, creditos,
                    int((time.monotonic() - inicio) * 1000))
        return execucao
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()


def _pode_exceder(sessao: Session, tenant_id: str, falta: Decimal) -> bool:
    if comercial.modo_cobranca() == "MEASURE":
        return True
    config = carteira.configuracao(sessao, tenant_id)
    if not (config.excedente_ativo and config.excedente_aprovado_por):
        return False
    if config.excedente_limite_rigido is None:
        return True
    return carteira.excedente_no_mes(sessao, tenant_id) + falta <= Decimal(config.excedente_limite_rigido)


def registrar_chamada(sessao: Session, execucao_id: str, custo_usd: Decimal | None, economia_cache_usd: Decimal | None,
                      cache_hit: bool, custo_dados_usd: Decimal | None = None) -> None:
    """Chamado pelo gateway na MESMA transação do evento de uso."""
    execucao = sessao.get(ExecucaoIa, execucao_id)
    if execucao is None:
        return
    execucao.chamadas = (execucao.chamadas or 0) + 1
    if custo_usd is None and not cache_hit:
        execucao.custo_desconhecido = True
    execucao.custo_llm_usd = _d(execucao.custo_llm_usd) + _d(custo_usd)
    execucao.custo_dados_usd = _d(execucao.custo_dados_usd) + _d(custo_dados_usd)
    execucao.custo_total_usd = _d(execucao.custo_llm_usd) + _d(execucao.custo_dados_usd)
    execucao.economia_cache_usd = _d(execucao.economia_cache_usd) + _d(economia_cache_usd)
    execucao.cache_hits = (execucao.cache_hits or 0) + (1 if cache_hit else 0)
    _atualizar_economia(execucao)


def _atualizar_economia(execucao: ExecucaoIa) -> None:
    cambio = comercial.cambio_usd_brl()
    execucao.cambio_usd_brl = cambio
    custo_brl = None if cambio is None or execucao.custo_desconhecido else (_d(execucao.custo_total_usd) * cambio).quantize(Decimal("0.0001"))
    execucao.custo_total_brl = custo_brl
    receita = execucao.receita_brl
    if receita is None or custo_brl is None:
        execucao.lucro_bruto_brl = None
        execucao.margem_bruta = None
        return
    receita = _d(receita)
    execucao.lucro_bruto_brl = receita - custo_brl
    execucao.margem_bruta = ((receita - custo_brl) / receita).quantize(Decimal("0.0001")) if receita > 0 else None


def liquidar(db: Session, execucao_id: str, creditos: Decimal | None = None) -> ExecucaoIa:
    sessao = _sessao(db)
    try:
        execucao = sessao.get(ExecucaoIa, execucao_id)
        if execucao is None:
            raise NaoEncontrado(f"Execução {execucao_id} não encontrada.")
        carteira.travar(sessao, execucao.tenant_id)
        sessao.refresh(execucao)
        if execucao.status != "RESERVADA":  # idempotente: já liquidada/liberada
            return execucao
        real = _d(creditos) if creditos is not None else _d(execucao.creditos_estimados)
        reservado = _d(execucao.creditos_reservados)
        execucao.creditos_reservados = ZERO
        if reservado > 0:
            carteira.movimentar(sessao, execucao.tenant_id, Evento.RELEASED, reservado, execucao=execucao, descricao="liquidação")
        consumido, receita, falta = carteira.consumir(sessao, execucao.tenant_id, real, execucao) if real > 0 else (ZERO, ZERO, ZERO)
        excedente = ZERO
        if falta > 0:
            config = carteira.configuracao(sessao, execucao.tenant_id)
            if config.excedente_ativo and config.excedente_aprovado_por:
                lote = carteira.lote_excedente(sessao, execucao.tenant_id)
                lote.quantidade_restante = _d(lote.quantidade_restante) - falta
                receita_excedente = (falta * _d(lote.receita_por_credito_brl)).quantize(Decimal("0.0001"))
                carteira.movimentar(sessao, execucao.tenant_id, Evento.OVERAGE, -falta, lote=lote, execucao=execucao,
                                    receita=receita_excedente, descricao="Excedente pós-pago", faturavel=True)
                receita += receita_excedente
                excedente = falta
            elif comercial.modo_cobranca() == "MEASURE":
                carteira.movimentar(sessao, execucao.tenant_id, Evento.OVERAGE, -falta, execucao=execucao, receita=ZERO,
                                    descricao="Consumo sem saldo (modo MEASURE, não faturável)")
                excedente = falta
            else:
                logger.warning("CREDITOS_NAO_COBRADOS execucao=%s falta=%s", execucao.id, falta)
        execucao.creditos_liquidados = consumido
        execucao.creditos_excedente = excedente
        execucao.receita_brl = receita
        execucao.status = "LIQUIDADA"
        execucao.liquidado_em = carteira.agora_utc()
        _atualizar_economia(execucao)
        sessao.commit()
        limites.registrar_alertas(sessao, execucao.tenant_id)
        sessao.commit()
        _recarga_automatica(sessao, execucao.tenant_id)
        return execucao
    except Exception:
        sessao.rollback()
        logger.error("CREDITOS_LIQUIDACAO_FALHOU execucao=%s", execucao_id, exc_info=True)
        raise
    finally:
        sessao.close()


def _recarga_automatica(sessao: Session, tenant_id: str) -> None:
    from app.contexts.finops import compras  # evita ciclo

    try:
        compras.verificar_recarga_automatica(sessao, tenant_id)
    except Exception:  # noqa: BLE001 — falha de recarga nunca derruba a operação já liquidada
        sessao.rollback()
        logger.error("CREDITOS_RECARGA_FALHOU tenant=%s", tenant_id, exc_info=True)


def liberar(db: Session, execucao_id: str, motivo: str) -> ExecucaoIa:
    """Falha antes de resultado utilizável: devolve a reserva, nada é cobrado."""
    sessao = _sessao(db)
    try:
        execucao = sessao.get(ExecucaoIa, execucao_id)
        if execucao is None:
            raise NaoEncontrado(f"Execução {execucao_id} não encontrada.")
        carteira.travar(sessao, execucao.tenant_id)
        sessao.refresh(execucao)
        if execucao.status != "RESERVADA":
            return execucao
        reservado = _d(execucao.creditos_reservados)
        execucao.creditos_reservados = ZERO
        execucao.status = "LIBERADA"
        execucao.motivo_estorno = motivo[:300]
        execucao.receita_brl = ZERO
        _atualizar_economia(execucao)
        if reservado > 0:
            carteira.movimentar(sessao, execucao.tenant_id, Evento.RELEASED, reservado, execucao=execucao, descricao=motivo[:300])
        sessao.commit()
        return execucao
    finally:
        sessao.close()


def estornar(db: Session, execucao_id: str, motivo: str, ator_id: str | None = None, tenant_id: str | None = None) -> ExecucaoIa:
    """Resultado inutilizável depois de liquidada (ou decisão administrativa)."""
    sessao = _sessao(db)
    try:
        execucao = sessao.get(ExecucaoIa, execucao_id)
        if execucao is None or (tenant_id is not None and execucao.tenant_id != tenant_id):
            raise NaoEncontrado(f"Execução {execucao_id} não encontrada.")
        carteira.travar(sessao, execucao.tenant_id)
        sessao.refresh(execucao)
        if execucao.status == "RESERVADA":
            sessao.close()
            return liberar(db, execucao_id, motivo)
        if execucao.status != "LIQUIDADA":
            return execucao
        carteira.estornar_consumo(sessao, execucao, motivo, ator_id)
        execucao.status = "ESTORNADA"
        execucao.motivo_estorno = motivo[:300]
        execucao.receita_brl = ZERO
        _atualizar_economia(execucao)
        from app.services import auditoria_service

        from app.models.carteira_creditos import MovimentoCredito

        ultimo = sessao.query(MovimentoCredito.id).filter_by(execucao_id=execucao.id).order_by(MovimentoCredito.id.desc()).first()
        auditoria_service.registrar(sessao, execucao.tenant_id, "creditos_ia_estornados", "movimento_credito", ultimo[0] if ultimo else 0, ator_id, {
            "execucao_id": execucao.id, "motivo": motivo, "creditos": float(_d(execucao.creditos_liquidados)),
        })
        sessao.commit()
        return execucao
    finally:
        sessao.close()


@contextmanager
def executar(db: Session, tenant_id: str, workload_codigo: str, **kwargs) -> Iterator[ExecucaoIa]:
    """Execução explícita: as chamadas feitas dentro do bloco (com
    `ContextoIA(execucao_id=...)`) somam custo nela; o crédito é
    liquidado uma vez no fim. Exceção = reserva liberada, nada cobrado."""
    execucao = abrir(db, tenant_id, workload_codigo, **kwargs)
    if execucao.status != "RESERVADA":  # retry de algo já concluído: não cobra de novo
        yield execucao
        return
    try:
        yield execucao
    except Exception as erro:
        liberar(db, execucao.id, f"falha sem resultado: {type(erro).__name__}")
        raise
    liquidar(db, execucao.id)


def liberar_reservas_orfas(db: Session, minutos: int = 30) -> int:
    """Cron: reserva esquecida (processo morto) não prende saldo para sempre."""
    from datetime import timedelta

    limite = carteira.agora_utc() - timedelta(minutes=minutos)
    ids = [e.id for e in db.query(ExecucaoIa).filter(ExecucaoIa.status == "RESERVADA", ExecucaoIa.criado_em < limite).all()]
    for execucao_id in ids:
        liberar(db, execucao_id, "reserva expirada sem conclusão")
    return len(ids)
