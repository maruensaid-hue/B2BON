"""Algoritmo único de risco de churn do MAP.

Antes da Fase 1 a mesma soma de pontos estava duplicada em
`motor_service.calcular_score_risco` (sujeito = tenant assinante) e
`saude_conta_service.calcular_score_risco_da_conta` (sujeito = conta).
Agora os dois chamam `calcular_score`, e só o que difere entre eles
(de onde vêm as interações, o fallback do último contato e os limiares)
fica com quem chama. Função pura: não toca em banco.
"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Protocol

TIPOS_VALIDOS = frozenset(
    {
        "contato",
        "ticket_suporte",
        "reclamacao",
        "feedback_positivo",
        "reuniao_remarcada",
        "mencionou_concorrente",
    }
)
TIPOS_CONTATO = frozenset({"contato", "feedback_positivo"})
JANELA_SINAIS_DIAS = 30


class Interacao(Protocol):
    tipo: str
    criado_em: datetime


def _utc(momento: datetime) -> datetime:
    return momento.replace(tzinfo=UTC)


def calcular_score(interacoes: Iterable[Interacao], ultimo_contato_fallback: datetime, agora: datetime | None = None) -> dict:
    """`interacoes` em ordem decrescente de `criado_em` (a mais recente
    primeiro) — é o que define o "último contato". Devolve `score`
    (0–100), `dias_sem_contato` e `sinais` (quanto cada regra somou)."""
    interacoes = list(interacoes)
    agora = agora or datetime.now(UTC)

    ultimo_contato_em = next((i.criado_em for i in interacoes if i.tipo in TIPOS_CONTATO), None)
    if ultimo_contato_em is None:
        ultimo_contato_em = ultimo_contato_fallback

    dias_sem_contato = (agora - _utc(ultimo_contato_em)).days

    score = 10.0
    sinais: dict[str, int] = {}

    if dias_sem_contato > 30:
        score += 30
        sinais["dias_sem_contato"] = 30
    elif dias_sem_contato > 14:
        score += 20
        sinais["dias_sem_contato"] = 20
    elif dias_sem_contato > 7:
        score += 10
        sinais["dias_sem_contato"] = 10

    corte = agora - timedelta(days=JANELA_SINAIS_DIAS)
    recentes = [i for i in interacoes if _utc(i.criado_em) >= corte]

    reclamacoes_recentes = sum(1 for i in recentes if i.tipo == "reclamacao")
    if reclamacoes_recentes:
        pontos = min(reclamacoes_recentes * 15, 45)
        score += pontos
        sinais["reclamacoes"] = pontos

    if any(i.tipo == "mencionou_concorrente" for i in recentes):
        score += 20
        sinais["mencionou_concorrente"] = 20

    if any(i.tipo == "reuniao_remarcada" for i in recentes):
        score += 15
        sinais["reuniao_remarcada"] = 15

    if any(i.tipo == "feedback_positivo" for i in recentes):
        score -= 20
        sinais["feedback_positivo"] = -20

    return {
        "score": max(0.0, min(100.0, score)),
        "dias_sem_contato": dias_sem_contato,
        "sinais": sinais,
    }


def classificar(score: float, limiar_critico: float, limiar_atencao: float) -> str:
    if score >= limiar_critico:
        return "critico"
    if score >= limiar_atencao:
        return "atencao"
    return "saudavel"
