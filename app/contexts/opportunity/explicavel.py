"""Contrato de explicabilidade (GATE da Fase 6).

Toda recomendação do Opportunity Intelligence carrega motivo, evidências,
confiança, fonte (qual motor/regra gerou) e data de geração. Uma
recomendação sem evidência não pode ser construída: `recomendacao()`
recusa. Falta de dado vira `INSUFFICIENT_INFORMATION` com a lista do que
falta (§23), e a própria lacuna é a evidência.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
METODOLOGIA = "RULE_BASED_V1"


class Confianca(StrEnum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"


class FonteEvidencia(StrEnum):
    CONFIRMADO_POR_HUMANO = "confirmado_por_humano"
    SUGESTAO_IA = "sugestao_ia_nao_confirmada"
    CADASTRO = "cadastro"
    CALCULO = "calculo_deterministico"
    AUSENCIA = "ausencia_de_dado"


@dataclass(frozen=True)
class Evidencia:
    tipo: str
    referencia: str | int | None
    trecho: str
    fonte: FonteEvidencia


@dataclass(frozen=True)
class Recomendacao:
    tipo: str
    titulo: str
    motivo: str
    evidencias: tuple[Evidencia, ...]
    confianca: Confianca
    fonte: str
    gerado_em: datetime
    dados: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        resultado = asdict(self)
        resultado["evidencias"] = [asdict(e) for e in self.evidencias]
        return resultado


def recomendacao(
    tipo: str,
    titulo: str,
    motivo: str,
    evidencias: list[Evidencia],
    confianca: Confianca,
    fonte: str,
    *,
    gerado_em: datetime | None = None,
    dados: dict | None = None,
) -> Recomendacao:
    if not motivo.strip():
        raise ValueError(f"Recomendação '{titulo}' sem motivo.")
    if not evidencias:
        raise ValueError(f"Recomendação '{titulo}' sem evidência.")
    if not fonte:
        raise ValueError(f"Recomendação '{titulo}' sem fonte.")
    return Recomendacao(
        tipo=tipo,
        titulo=titulo,
        motivo=motivo,
        evidencias=tuple(evidencias),
        confianca=Confianca(confianca),
        fonte=fonte,
        gerado_em=gerado_em or datetime.now(UTC),
        dados=dados or {},
    )
