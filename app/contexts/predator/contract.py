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
    registrar_candidatos,
)
from app.contexts.predator.prospeccao import _score_aderencia as score_aderencia
from app.contexts.predator import ri  # documentos de RI e indicadores (V5.2.1, Fase 5): `predator.contract.ri`
from app.contexts.predator import sinais  # sinais de conta, critérios do ICP e coorte: `predator.contract.sinais`
from app.contexts.predator import portao_envio  # checagem determinística antes do envio: `predator.contract.portao_envio`
from app.contexts.predator import optout_resposta  # descadastro escrito na resposta: `predator.contract.optout_resposta`
from app.contexts.predator import descoberta  # descoberta paga por busca de mapa (estima antes): `predator.contract.descoberta`

__all__ = [
    "ri",
    "sinais",
    "portao_envio",
    "optout_resposta",
    "descoberta",
    "enfileirar_enriquecimento_em_lote",
    "enriquecer",
    "enriquecer_via_brasilapi",
    "gerar_lista",
    "mapear_decisores",
    "registrar_candidatos",
    "score_aderencia",
]
