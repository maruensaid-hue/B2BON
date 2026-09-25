"""Context Engine (Fase 4, Master Prompt §58).

    USER REQUEST → INTENT → AUTHORIZATION → PURPOSE → AUTHORIZED RETRIEVAL
    → MINIMUM RELEVANT CONTEXT → MODEL

Nunca envia o Corporate Brain inteiro: busca só o relevante para a
consulta, filtra pelo PROPÓSITO (o que pode ser usado para quê),
respeita um orçamento de caracteres e devolve a proveniência de cada
item usado (para explicabilidade, §63). RESTRICTED nunca vai para LLM.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.orm import Session

from app.contexts.intelligence import brain, prompt_seguro
from app.contexts.shared.canonical.base import DataClassification


class Proposito(StrEnum):
    USO_INTERNO = "uso_interno"  # responder ao próprio tenant
    RESPOSTA_EXTERNA = "resposta_externa"  # responder a outra empresa (Agente Corporativo, Rede)


_POLITICA = {
    Proposito.USO_INTERNO: (
        frozenset({"interno", "rede"}),
        frozenset({DataClassification.PUBLIC.value, DataClassification.INTERNAL.value, DataClassification.CONFIDENTIAL.value}),
    ),
    Proposito.RESPOSTA_EXTERNA: (
        frozenset({"rede"}),
        frozenset({DataClassification.PUBLIC.value, DataClassification.INTERNAL.value}),
    ),
}


@dataclass(frozen=True)
class ContextoMontado:
    texto: str
    fontes: list[dict] = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not self.fontes


def montar(db: Session, tenant_id: str, proposito: Proposito, consulta: str, *, max_caracteres: int = 4000, limite_itens: int = 5) -> ContextoMontado:
    if not tenant_id:
        raise ValueError("Context Engine exige tenant_id.")
    visibilidades, classificacoes = _POLITICA[proposito]
    encontrados = brain.buscar(db, tenant_id, consulta, visibilidades=visibilidades, classificacoes=classificacoes, limite=limite_itens)
    partes: list[str] = []
    fontes: list[dict] = []
    restante = max_caracteres
    for item, pontos in encontrados:
        trecho = f"[{item.tipo}] {item.titulo}: {item.conteudo}"
        if restante <= 0:
            break
        trecho = trecho[:restante]
        restante -= len(trecho)
        partes.append(prompt_seguro.neutralizar(trecho))
        fontes.append({"id": item.id, "tipo": item.tipo, "titulo": item.titulo, "origem": item.origem, "fonte": item.fonte, "aderencia": pontos})
    return ContextoMontado(texto="\n".join(partes), fontes=fontes)
