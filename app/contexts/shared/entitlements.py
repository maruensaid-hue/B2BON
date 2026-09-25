"""Entitlements do tenant — Shared Kernel (Master Prompt §74).

Fachada fina sobre `PlanLimitsProvider`, que continua sendo a fonte dos
dados de plano. Existe para que quem decide acesso pergunte por nome
(`has_module("map")`, `has_feature("AUTO_APROVACAO")`) em vez de chamar
um método por flag. A validação é sempre no backend; o frontend só
espelha (`recursos_plano`).
"""

from collections.abc import Callable

from app.providers.plan_limits.base import PlanLimitsProvider

# "bids" (Fase 9): Bid Intelligence, vendido na suíte B2B ON Public Sector
# (§70). Não entra em nenhum plano existente sozinho: um plano só o libera
# quando o super_admin inclui "bids" em `modulos_contratados` (sem preço
# novo; catálogo na Fase 14).
# "procurement" (Fase 10): B2B ON Public Procurement, lado comprador. Preço
# PENDING_DEFINITION (§71): nenhum plano o inclui até o PO definir.
MODULOS = ("map", "predator", "crm", "bids", "procurement")
NOMES_MODULO = {
    "map": "MAP", "predator": "PREDATOR", "crm": "CRM", "bids": "Bid Intelligence", "procurement": "Public Procurement",
}

_FEATURES: dict[str, Callable[[PlanLimitsProvider, str], bool]] = {
    "AB_TESTE_CADENCIA": lambda p, t: p.permite_ab_teste_cadencia(t),
    "AUTO_APROVACAO": lambda p, t: p.permite_auto_aprovacao(t),
    "WEBHOOK_RELATORIO": lambda p, t: p.permite_webhook_relatorio(t),
    "API_PARCEIROS": lambda p, t: p.permite_api_parceiros(t),
    "SUBTENANTS": lambda p, t: p.permite_subtenants(t),
    "REGISTRO_OPORTUNIDADE": lambda p, t: p.permite_registro_oportunidade(t),
}
FEATURES = tuple(_FEATURES)


class Entitlements:
    def __init__(self, plan_limits: PlanLimitsProvider, tenant_id: str) -> None:
        self._plan_limits = plan_limits
        self._tenant_id = tenant_id

    def has_module(self, modulo: str) -> bool:
        if modulo not in MODULOS:
            raise ValueError(f"Módulo desconhecido: {modulo}")
        return self._plan_limits.permite_modulo(self._tenant_id, modulo)

    def has_any_module(self, *modulos: str) -> bool:
        return any(self.has_module(modulo) for modulo in modulos)

    def has_feature(self, feature: str) -> bool:
        verificar = _FEATURES.get(feature)
        if verificar is None:
            raise ValueError(f"Feature desconhecida: {feature}")
        return verificar(self._plan_limits, self._tenant_id)
