"""Budget guard, limiares de uso e proteção contra abuso (Fase 15).

- Budget guard do tenant (opcional; cliente simples não configura nada):
  orçamento mensal, limite diário, por usuário, por módulo (% do
  orçamento), por agente e para chamadas de API. Com `parada_rigida`,
  estourar bloqueia antes de chamar o modelo; sem, só alerta.
- Limiares de uso do período (80/95/100%) viram alerta uma vez por nível.
- Previsão de dias restantes só com amostra suficiente.
- Base de detecção de anomalia: consumo da última hora muito acima da
  média horária dos últimos 7 dias.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.finops import carteira, comercial
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import AlertaCreditos, ExecucaoIa
from app.services.errors import OrcamentoIaExcedido

logger = logging.getLogger("b2bon.creditos")
ZERO = Decimal(0)


def _inicio_mes(agora):
    return agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def consumo(db: Session, tenant_id: str, desde, **filtros) -> Decimal:
    """Créditos liquidados + reservados (em curso) desde `desde`."""
    consulta = db.query(func.sum(ExecucaoIa.creditos_liquidados + ExecucaoIa.creditos_excedente),
                        func.sum(ExecucaoIa.creditos_reservados)).filter(
        ExecucaoIa.tenant_id == tenant_id, ExecucaoIa.criado_em >= desde, ExecucaoIa.status.in_(("RESERVADA", "LIQUIDADA")))
    for campo, valor in filtros.items():
        consulta = consulta.filter(getattr(ExecucaoIa, campo) == valor)
    liquidado, reservado = consulta.one()
    return Decimal(str(liquidado or 0)) + Decimal(str(reservado or 0))


def consumido_no_mes(db: Session, tenant_id: str, agora=None) -> Decimal:
    agora = agora or carteira.agora_utc()
    return -Decimal(str(db.query(func.sum(MovimentoCredito.quantidade)).filter(
        MovimentoCredito.tenant_id == tenant_id, MovimentoCredito.tipo.in_(("CREDIT_CONSUMED", "CREDIT_REFUNDED")),
        MovimentoCredito.criado_em >= _inicio_mes(agora)).scalar() or 0))


def verificar_orcamento(db: Session, tenant_id: str, creditos: Decimal, *, modulo: str, agente: str | None,
                        usuario_id: int | None, gatilho: str | None) -> list[str]:
    """Levanta `OrcamentoIaExcedido` (parada rígida) ou devolve avisos."""
    config = carteira.configuracao(db, tenant_id)
    agora = carteira.agora_utc()
    mes = _inicio_mes(agora)
    estouros: list[str] = []
    avisos: list[str] = []

    def checar(nome: str, usado: Decimal, limite) -> None:
        if limite is None:
            return
        limite = Decimal(str(limite))
        if usado + creditos > limite:
            estouros.append(f"{nome} ({int(limite)} créditos)")
        elif limite and (usado + creditos) / limite * 100 >= config.percentual_alerta:
            avisos.append(f"{nome} acima de {config.percentual_alerta}%")

    checar("orçamento mensal de IA", consumo(db, tenant_id, mes), config.orcamento_mensal_creditos)
    checar("limite diário de IA", consumo(db, tenant_id, agora.replace(hour=0, minute=0, second=0, microsecond=0)),
           config.limite_diario_creditos)
    if usuario_id is not None:
        checar("limite por usuário", consumo(db, tenant_id, mes, usuario_id=usuario_id), config.limite_usuario_creditos)
    if gatilho == "api":
        checar("limite de API", consumo(db, tenant_id, mes, gatilho="api"), config.limite_api_creditos)
    if agente and config.limites_agente_creditos and agente in config.limites_agente_creditos:
        checar(f"limite do agente {agente}", consumo(db, tenant_id, mes, agente=agente), config.limites_agente_creditos[agente])
    percentual = (config.limites_modulo_percentual or {}).get(modulo)
    if percentual is not None:
        base = Decimal(str(config.orcamento_mensal_creditos)) if config.orcamento_mensal_creditos else (
            carteira.disponivel(db, tenant_id) + consumido_no_mes(db, tenant_id, agora))
        checar(f"limite do módulo {modulo} ({int(Decimal(str(percentual)) * 100)}%)", consumo(db, tenant_id, mes, modulo=modulo),
               (base * Decimal(str(percentual))).quantize(Decimal("1")))
    if estouros:
        if config.parada_rigida:
            raise OrcamentoIaExcedido("Orçamento de IA atingido: " + "; ".join(estouros) + ".")
        avisos.extend(f"{e} excedido" for e in estouros)
    return avisos


def uso_do_periodo(db: Session, tenant_id: str, agora=None) -> dict:
    agora = agora or carteira.agora_utc()
    disponivel = carteira.disponivel(db, tenant_id, agora)
    consumido = consumido_no_mes(db, tenant_id, agora)
    pool = disponivel + consumido
    percentual = float((consumido / pool * 100).quantize(Decimal("0.1"))) if pool > 0 else None
    return {"periodo": agora.strftime("%Y-%m"), "disponivel": float(disponivel), "consumido": float(consumido),
            "total_do_periodo": float(pool), "percentual": percentual, "dias_restantes_estimados": dias_restantes(db, tenant_id, agora)}


def dias_restantes(db: Session, tenant_id: str, agora=None) -> int | None:
    """Disponível ÷ média diária recente; None sem amostra suficiente."""
    agora = agora or carteira.agora_utc()
    desde = agora - timedelta(days=comercial.DIAS_AMOSTRA_PREVISAO)
    linhas = db.query(func.date(MovimentoCredito.criado_em), func.sum(MovimentoCredito.quantidade)).filter(
        MovimentoCredito.tenant_id == tenant_id, MovimentoCredito.tipo == "CREDIT_CONSUMED", MovimentoCredito.criado_em >= desde,
    ).group_by(func.date(MovimentoCredito.criado_em)).all()
    if len(linhas) < comercial.MIN_DIAS_COM_USO_PREVISAO:
        return None
    media = -sum(Decimal(str(v or 0)) for _, v in linhas) / comercial.DIAS_AMOSTRA_PREVISAO
    if media <= 0:
        return None
    return int(carteira.disponivel(db, tenant_id, agora) / media)


def registrar_alertas(db: Session, tenant_id: str, agora=None) -> list[int]:
    """Cria um alerta por nível atingido no período (idempotente)."""
    uso = uso_do_periodo(db, tenant_id, agora)
    novos = []
    if uso["percentual"] is None:
        return novos
    for nivel in comercial.LIMIARES_USO:
        if uso["percentual"] >= nivel:
            if db.query(AlertaCreditos.id).filter_by(tenant_id=tenant_id, periodo=uso["periodo"], nivel=nivel).first():
                continue
            try:
                with db.begin_nested():
                    db.add(AlertaCreditos(tenant_id=tenant_id, periodo=uso["periodo"], nivel=nivel, percentual=uso["percentual"]))
                novos.append(nivel)
                logger.warning("CREDITOS_LIMIAR tenant=%s nivel=%s%% uso=%s%%", tenant_id, nivel, uso["percentual"])
            except IntegrityError:
                continue
    return novos


def alertas(db: Session, tenant_id: str, periodo: str | None = None) -> list[dict]:
    consulta = db.query(AlertaCreditos).filter_by(tenant_id=tenant_id)
    if periodo:
        consulta = consulta.filter_by(periodo=periodo)
    return [{"periodo": a.periodo, "nivel": a.nivel, "percentual": float(a.percentual),
             "tipo": "LIMIT_POLICY" if a.nivel >= 100 else ("CRITICAL_WARNING" if a.nivel >= 95 else "WARNING"),
             "criado_em": a.criado_em.isoformat() if a.criado_em else None}
            for a in consulta.order_by(AlertaCreditos.id.desc()).limit(50).all()]


def anomalia_de_consumo(db: Session, tenant_id: str, agora=None, fator: Decimal = Decimal(10), minimo: Decimal = Decimal(500)) -> dict | None:
    """Pico: última hora > `fator` × média horária dos 7 dias anteriores e acima de `minimo`."""
    agora = agora or carteira.agora_utc()
    ultima_hora = consumo(db, tenant_id, agora - timedelta(hours=1))
    semana = consumo(db, tenant_id, agora - timedelta(days=7)) - ultima_hora
    media_hora = semana / (7 * 24)
    if ultima_hora >= minimo and ultima_hora > fator * max(media_hora, Decimal(1)):
        logger.warning("CREDITOS_PICO tenant=%s ultima_hora=%s media_hora=%s", tenant_id, ultima_hora, media_hora)
        return {"ultima_hora": float(ultima_hora), "media_horaria_7d": float(media_hora.quantize(Decimal("0.01")))}
    return None
