"""Contrato público do contexto PREDATOR (Fase 1).

Código de fora do PREDATOR (routers, serviços legados, futura API
`/api/v1/predator/*`) chama a prospecção por aqui.
"""

from app.contexts.predator.prospeccao import (
    enfileirar_enriquecimento_em_lote,
    enriquecer,
    enriquecer_via_brasilapi,
    gerar_lista,
    mapear_decisores,
)
from app.contexts.predator.prospeccao import _score_aderencia as score_aderencia

__all__ = [
    "enfileirar_enriquecimento_em_lote",
    "enriquecer",
    "enriquecer_via_brasilapi",
    "gerar_lista",
    "mapear_decisores",
    "score_aderencia",
]
