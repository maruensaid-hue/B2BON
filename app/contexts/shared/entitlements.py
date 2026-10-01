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
MODULOS = ("map", "predator", "crm", "bids", "procurement", "sourcing")
NOMES_MODULO = {
    "map": "MAP", "predator": "PREDATOR", "crm": "CRM", "bids": "Bid Intelligence", "procurement": "Public Procurement",
    "sourcing": "Strategic Sourcing",
}

_FEATURES: dict[str, Callable[[PlanLimitsProvider, str], bool]] = {
    "AB_TESTE_CADENCIA": lambda p, t: p.permite_ab_teste_cadencia(t),
    "AUTO_APROVACAO": lambda p, t: p.permite_auto_aprovacao(t),
    "WEBHOOK_RELATORIO": lambda p, t: p.permite_webhook_relatorio(t),
    "API_PARCEIROS": lambda p, t: p.permite_api_parceiros(t),
    "SUBTENANTS": lambda p, t: p.permite_subtenants(t),
    "REGISTRO_OPORTUNIDADE": lambda p, t: p.permite_registro_oportunidade(t),
    # Phase I (D-059): tier Enterprise do Strategic Sourcing é feature do módulo `sourcing`, marcada no plano
    # pela chave `sourcing_enterprise` (não é módulo à parte nem entra em `MODULOS`).
    "SOURCING_ENTERPRISE": lambda p, t: p.permite_modulo(t, "sourcing") and p.permite_modulo(t, "sourcing_enterprise"),
}
FEATURES = tuple(_FEATURES)

# D-076: capabilities do Public Procurement. Um motor só (módulo `procurement`); o nível do plano (BASIC | FULL) define
# o que fica disponível. Plano sem nível (privado) tem todas, como antes.
CAPACIDADES_PUBLIC_PROCUREMENT_BASIC = (
    "demand_management", "process_workspace", "pca_support", "supplier_registry", "basic_price_research",
    "document_management", "tasks", "deadlines", "basic_workflow", "contract_tracking", "procurement_dashboard", "audit_trail",
)
CAPACIDADES_PUBLIC_PROCUREMENT = {
    "BASIC": CAPACIDADES_PUBLIC_PROCUREMENT_BASIC,
    "FULL": CAPACIDADES_PUBLIC_PROCUREMENT_BASIC + (
        "supplier_360", "procurement_graph", "document_intelligence", "etp_intelligence", "tr_intelligence", "tender_intelligence",
        "compliance_matrix", "evaluation_engine", "procurement_agent", "next_best_action", "risk_engine", "proposal_comparison",
        "contract_intelligence", "sla_monitoring", "amendment_intelligence", "renewal_intelligence", "advanced_analytics",
        "apis_integrations",
    ),
}

# Phase J3 (OI-023): papéis de quem é de fora da empresa (ex.: fornecedor convidado a responder um processo)
# nunca ocupam assento interno. Hoje o Supplier Guest entra por link, sem usuário; se um papel externo passar a
# existir como usuário, ele é declarado aqui e continua fora da contagem.
PAPEIS_EXTERNOS = frozenset({"supplier_guest"})


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

    def limite_usuarios(self) -> int | None:
        """Assentos internos: incluídos no plano + adicionais da licença; `None` = sem limite."""
        return self._plan_limits.obter_limite_usuarios(self._tenant_id)

    def has_feature(self, feature: str) -> bool:
        verificar = _FEATURES.get(feature)
        if verificar is None:
            raise ValueError(f"Feature desconhecida: {feature}")
        return verificar(self._plan_limits, self._tenant_id)

    def nivel_public_procurement(self) -> str:
        return self._plan_limits.obter_nivel_public_procurement(self._tenant_id) or "FULL"

    def has_capability(self, capacidade: str) -> bool:
        """Capability do Public Procurement (D-076): exige o módulo e o nível do plano que a inclui."""
        if capacidade not in CAPACIDADES_PUBLIC_PROCUREMENT["FULL"]:
            raise ValueError(f"Capability desconhecida: {capacidade}")
        nivel = self.nivel_public_procurement()
        return self.has_module("procurement") and capacidade in CAPACIDADES_PUBLIC_PROCUREMENT.get(nivel, ())
