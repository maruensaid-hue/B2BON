import httpx

from app.core.config import settings
from app.providers.payment.base import DetalhePagamento, PaymentProvider, PreferenciaCriada
from app.services.errors import RegraNegocioViolada

_BASE_URL = "https://api.mercadopago.com"


class MercadoPagoProvider(PaymentProvider):
    """Checkout Pro (pagamento único) — cadastro self-service com escolha
    de plano. Não usa a Preapproval API (assinatura recorrente): renovação
    é uma ação manual do cliente por enquanto, escopo deliberadamente
    reduzido para a primeira integração de cobrança da plataforma."""

    def __init__(self) -> None:
        self._headers = {"Authorization": f"Bearer {settings.mercadopago_access_token}"}

    def criar_preferencia(
        self, referencia_externa: str, descricao: str, valor: float, email_pagador: str
    ) -> PreferenciaCriada:
        corpo = {
            "items": [
                {
                    "title": descricao,
                    "quantity": 1,
                    "unit_price": valor,
                    "currency_id": "BRL",
                }
            ],
            "payer": {"email": email_pagador},
            "external_reference": referencia_externa,
            "back_urls": {
                "success": f"{settings.url_base_frontend}/pagamento/retorno",
                "pending": f"{settings.url_base_frontend}/pagamento/retorno",
                "failure": f"{settings.url_base_frontend}/pagamento/retorno",
            },
            "auto_return": "approved",
            "notification_url": f"{settings.url_base_api}/webhooks/mercadopago",
        }
        try:
            resposta = httpx.post(
                f"{_BASE_URL}/checkout/preferences", json=corpo, headers=self._headers, timeout=15.0
            )
            resposta.raise_for_status()
        except httpx.HTTPError as erro:
            raise RegraNegocioViolada(f"Não foi possível iniciar o pagamento: {erro}") from erro

        dados = resposta.json()
        return PreferenciaCriada(id_externo=dados["id"], url_checkout=dados["init_point"])

    def buscar_pagamento(self, pagamento_id_externo: str) -> DetalhePagamento:
        try:
            resposta = httpx.get(
                f"{_BASE_URL}/v1/payments/{pagamento_id_externo}", headers=self._headers, timeout=15.0
            )
            resposta.raise_for_status()
        except httpx.HTTPError as erro:
            raise RegraNegocioViolada(f"Não foi possível consultar o pagamento: {erro}") from erro

        dados = resposta.json()
        return DetalhePagamento(
            id_externo=str(dados["id"]),
            referencia_externa=dados.get("external_reference"),
            status=dados["status"],
            valor=float(dados["transaction_amount"]),
            taxas=_taxas(dados),
            valor_liquido=_liquido(dados),
        )


def _taxas(dados: dict) -> float | None:
    """Soma as tarifas que o próprio Mercado Pago informa (`fee_details`) e que ficam com o recebedor; sem a lista, não há valor (nunca se estima)."""
    detalhes = dados.get("fee_details")
    if not isinstance(detalhes, list) or not detalhes:
        return None
    try:
        return round(sum(float(item.get("amount") or 0) for item in detalhes if item.get("fee_payer", "collector") == "collector"), 2)
    except (TypeError, ValueError):
        return None


def _liquido(dados: dict) -> float | None:
    bruto = (dados.get("transaction_details") or {}).get("net_received_amount")
    try:
        return round(float(bruto), 2) if bruto is not None else None
    except (TypeError, ValueError):
        return None
