"""Política comercial dos B2B ON AI Credits (Fase 15) — FONTE ÚNICA.

Tudo o que é regra comercial e pode mudar (margem-alvo, faixas de alerta,
limiares de uso, validade, franquias por módulo, ordem de consumo) mora
aqui ou em `settings` lido só daqui. Preços de pacote e pesos de workload
não estão aqui: são dados versionados no banco (`catalogos.py`).

Nada neste módulo expõe tokens ao cliente: créditos são capacidade de
inteligência; tokens são unidade técnica interna.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.core.config import settings


class TipoLote(StrEnum):
    SUBSCRIPTION = "SUBSCRIPTION"
    TOPUP = "TOPUP"
    PROMOTIONAL = "PROMOTIONAL"
    ADJUSTMENT = "ADJUSTMENT"
    ENTERPRISE_OVERAGE = "ENTERPRISE_OVERAGE"


class Evento(StrEnum):
    GRANTED = "CREDIT_GRANTED"
    CONSUMED = "CREDIT_CONSUMED"
    EXPIRED = "CREDIT_EXPIRED"
    PURCHASED = "CREDIT_PURCHASED"
    REFUNDED = "CREDIT_REFUNDED"
    ADJUSTED = "CREDIT_ADJUSTED"
    PROMOTIONAL = "CREDIT_PROMOTIONAL"
    OVERAGE = "CREDIT_OVERAGE"
    RESERVED = "CREDIT_RESERVED"
    RELEASED = "CREDIT_RELEASED"


class Classe(StrEnum):
    C0 = "C0"  # determinístico, sem LLM
    C1 = "C1"  # IA econômica
    C2 = "C2"  # inteligência padrão
    C3 = "C3"  # inteligência avançada


PENDENTE = "PENDING_FINAL_DEFINITION"


@dataclass(frozen=True)
class Franquia:
    """Créditos mensais incluídos por produto. `creditos=None` com status
    PENDENTE = decisão futura do PO: nada é concedido por ela."""

    produto: str
    creditos: int | None
    status: str = "ATIVA"  # ATIVA | ADDON | PENDING_FINAL_DEFINITION | CUSTOM
    faixa: str | None = None
    observacao: str | None = None


# Configuração inicial de referência (prompt da Fase 15, §7).
FRANQUIAS: dict[str, Franquia] = {
    "crm": Franquia("crm", 5_000, observacao="Plano de entrada"),
    "map": Franquia("map", 10_000),
    "predator": Franquia("predator", 20_000),
    "opportunity_intelligence": Franquia("opportunity_intelligence", 10_000, "ADDON",
                                         observacao="Concedida quando contratada como add-on (hoje vem incluída no CRM, sem add-on à venda)"),
    "business_network": Franquia("business_network", 10_000, "ADDON",
                                 observacao="Concedida quando a Business Network Intelligence for contratada como add-on"),
    "bids": Franquia("bids", 25_000),
    # Phase I (D-059): Strategic Sourcing 50K; o tier Enterprise substitui (não soma) com 100K
    "sourcing": Franquia("sourcing", 50_000),
    "sourcing_enterprise": Franquia("sourcing_enterprise", 100_000, observacao="Tier Enterprise: substitui a franquia do Strategic Sourcing"),
    "procurement": Franquia("procurement", None, PENDENTE, faixa="50.000–100.000"),
    "full_suite": Franquia("full_suite", None, PENDENTE, faixa="75.000–100.000",
                           observacao="Até a definição, a suíte recebe a soma das franquias dos módulos que contém"),
    "enterprise": Franquia("enterprise", None, "CUSTOM", observacao="Pool próprio por contrato"),
}

def franquias_publicas() -> list[dict]:
    """Franquias para páginas públicas. Pendentes aparecem como pendentes —
    nunca com um número inventado."""
    return [{"produto": f.produto, "creditos": f.creditos, "status": f.status, "faixa": f.faixa, "observacao": f.observacao}
            for f in FRANQUIAS.values()]


# Ordem de consumo: FEFO (primeiro a vencer, primeiro a sair). Empate: tipo
# que não gera receita primeiro (promocional/ajuste), depois assinatura, por
# último o que o cliente comprou (top-up) — reduz perda e protege o pago.
PRIORIDADE_TIPO = {
    TipoLote.PROMOTIONAL: 0, TipoLote.ADJUSTMENT: 1, TipoLote.SUBSCRIPTION: 2, TipoLote.TOPUP: 3,
    TipoLote.ENTERPRISE_OVERAGE: 4,
}
POLITICA_CONSUMO = "FEFO"
LIMIARES_USO = (80, 95, 100)
DIAS_AMOSTRA_PREVISAO = 7
MIN_DIAS_COM_USO_PREVISAO = 3


@dataclass(frozen=True)
class FaixasMargem:
    alvo: Decimal
    alerta: Decimal
    critica: Decimal


def faixas_margem() -> FaixasMargem:
    return FaixasMargem(Decimal(str(settings.ai_margem_alvo)), Decimal(str(settings.ai_margem_alerta)),
                        Decimal(str(settings.ai_margem_critica)))


def nivel_margem(margem: Decimal | float | None) -> str | None:
    if margem is None:
        return None
    faixas = faixas_margem()
    margem = Decimal(str(margem))
    if margem < faixas.critica:
        return "MARGIN_CRITICAL"
    if margem < faixas.alerta:
        return "MARGIN_WARNING"
    return "OK" if margem >= faixas.alvo else "ABAIXO_DO_ALVO"


def modo_cobranca() -> str:
    return settings.ai_creditos_modo.upper()


def limiar_confirmacao() -> Decimal:
    return Decimal(settings.ai_creditos_limiar_confirmacao)


def max_reservas_abertas() -> int:
    return settings.ai_creditos_max_reservas_abertas


def validade_topup_meses() -> int:
    return settings.ai_creditos_validade_topup_meses


def receita_por_credito_assinatura() -> Decimal:
    return Decimal(str(settings.ai_creditos_receita_ref_assinatura_1k_brl)) / 1000


def receita_por_credito_excedente() -> Decimal:
    return Decimal(str(settings.ai_creditos_receita_ref_excedente_1k_brl)) / 1000


def cambio_usd_brl() -> Decimal | None:
    return Decimal(str(settings.finops_cambio_usd_brl)) if settings.finops_cambio_usd_brl else None


def horas_cache_resposta() -> int:
    return settings.ai_cache_resposta_horas


def franquia_mensal(modulos: list[str], personalizada: int | None = None) -> tuple[int, list[dict]]:
    """Créditos mensais de um plano pelos módulos contratados. Enterprise com
    pool próprio usa `personalizada`. Franquias pendentes não somam."""
    if personalizada is not None:
        return personalizada, [{"produto": "enterprise", "creditos": personalizada, "status": "CUSTOM"}]
    detalhe = []
    total = 0
    if "sourcing_enterprise" in modulos:  # tier Enterprise substitui a franquia do Strategic Sourcing
        modulos = [m for m in modulos if m != "sourcing"]
    for modulo in modulos:
        franquia = FRANQUIAS.get(modulo)
        if franquia is None:
            continue
        concede = franquia.status == "ATIVA" and franquia.creditos
        detalhe.append({"produto": modulo, "creditos": franquia.creditos if concede else 0, "status": franquia.status,
                        "faixa": franquia.faixa})
        total += franquia.creditos if concede else 0
    return total, detalhe
