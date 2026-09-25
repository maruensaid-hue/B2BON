"""Model Router do AI Gateway (Fase 4, Master Prompt §53).

C0 — determinístico, sem LLM (o gateway recusa chamar).
C1 — econômico (extração curta, classificação, ajuda).
C2 — padrão (redação comercial, resumo, estratégia).
C3 — raciocínio avançado (análise documental longa: editais/TRs, Fases 9–10).

Ids vêm de configuração (`AI_MODELO_C1/C2/C3`); C2 vazio = o modelo que
já estava em produção (`ANTHROPIC_MODEL`), para não trocar modelo de
feature existente sem decisão explícita.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.core.config import settings


class ClasseModelo(StrEnum):
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"


@dataclass(frozen=True)
class ModeloRoteado:
    id: str
    classe: ClasseModelo
    aceita_amostragem: bool


# Modelos que rejeitam temperature/top_p/top_k com HTTP 400 (família atual).
# Enviar `temperature` para eles quebra a chamada — bug latente encontrado
# na Fase 4 (o provider sempre enviava 1.0; o default é `claude-sonnet-5`).
_PREFIXOS_SEM_AMOSTRAGEM = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-fable",
    "claude-mythos",
)


def aceita_amostragem(modelo_id: str) -> bool:
    return not modelo_id.startswith(_PREFIXOS_SEM_AMOSTRAGEM)


def modelo_para(classe: ClasseModelo) -> ModeloRoteado:
    if classe == ClasseModelo.C0:
        raise ValueError("Classe C0 é determinística: não chama LLM.")
    ids = {
        ClasseModelo.C1: settings.ai_modelo_c1 or settings.anthropic_model,
        ClasseModelo.C2: settings.ai_modelo_c2 or settings.anthropic_model,
        ClasseModelo.C3: settings.ai_modelo_c3 or settings.anthropic_model,
    }
    modelo_id = ids[classe]
    return ModeloRoteado(id=modelo_id, classe=classe, aceita_amostragem=aceita_amostragem(modelo_id))
