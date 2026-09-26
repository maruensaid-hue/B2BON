"""Evaluation Engine (S1, D-055): o mesmo motor responde às duas perguntas.

- direção PROPRIA (Sell): "atendemos este requisito?" — evidência = cofre,
  portfólio, perfil;
- direção PROPOSTA (Buy): "esta proposta atende este requisito?" — evidência
  = documentos da proposta (fluxo Enterprise, S8).

O motor não sabe de onde vem a evidência: recebe **regras** em ordem. A
primeira que decidir vale; se nenhuma decidir, o resultado é UNKNOWN (falta
de dado nunca vira "não atende"). Requisito ainda só sugerido pela IA é
REQUIRES_REVIEW antes de qualquer regra. Ajuste humano prevalece, com
justificativa, e o status calculado continua visível.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from app.contexts.sourcing.tipos import STATUS_CONFORMIDADE


class Direcao(StrEnum):
    PROPRIA = "SELF"
    PROPOSTA = "PROPOSAL"


@dataclass(frozen=True)
class Decisao:
    status: str
    motivo: str
    evidencia: list[dict] = field(default_factory=list)
    risco: str | None = None
    fonte: str | None = None


# Uma regra recebe o requisito (qualquer objeto) e decide, ou devolve None para passar adiante.
Regra = Callable[[object], Decisao | None]

MOTIVO_SUGERIDO = "Requisito extraído pela IA e ainda não confirmado."


def decidir(requisito: object, regras: Iterable[Regra], sugerido: bool, sem_decisao: Callable[[object], Decisao]) -> Decisao:
    if sugerido:
        return Decisao("REQUIRES_REVIEW", MOTIVO_SUGERIDO)
    for regra in regras:
        decisao = regra(requisito)
        if decisao is not None:
            if decisao.status not in STATUS_CONFORMIDADE:
                raise ValueError(f"Status de conformidade inválido: {decisao.status}")
            return decisao
    return sem_decisao(requisito)


def ajustar(linha: dict, status_manual: str | None, ajuste: dict | None) -> dict:
    """Ajuste humano prevalece sobre o calculado, que continua em `status_calculado`."""
    if status_manual:
        linha["status"] = status_manual
        linha["ajuste_manual"] = ajuste
    return linha


def contar(linhas: list[dict]) -> dict[str, int]:
    contagem = dict.fromkeys(STATUS_CONFORMIDADE, 0)
    for linha in linhas:
        contagem[linha["status"]] += 1
    return contagem
