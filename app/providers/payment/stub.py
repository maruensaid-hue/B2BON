from app.providers.payment.base import DetalhePagamento, PaymentProvider, PreferenciaCriada
from app.services.errors import NaoEncontrado


class StubPaymentProvider(PaymentProvider):
    """Dev/teste — nunca chama rede. `aprovar()` simula o que o Mercado
    Pago faria de verdade (gera um id de pagamento e marca como aprovado),
    permitindo testar o fluxo do webhook de ponta a ponta sem credencial
    real (a implementação de verdade fica em `MercadoPagoProvider`)."""

    def __init__(self) -> None:
        self._preferencias: dict[str, dict] = {}
        self._contador = 0

    def criar_preferencia(
        self, referencia_externa: str, descricao: str, valor: float, email_pagador: str
    ) -> PreferenciaCriada:
        self._contador += 1
        id_externo = f"stub-pref-{self._contador}"
        self._preferencias[id_externo] = {
            "referencia_externa": referencia_externa,
            "valor": valor,
            "status": "pending",
            "pagamento_id": None,
        }
        return PreferenciaCriada(id_externo=id_externo, url_checkout=f"https://checkout.stub.local/{id_externo}")

    def aprovar(self, id_externo_preferencia: str) -> str:
        """Só para teste — não faz parte da porta `PaymentProvider`."""
        self._contador += 1
        pagamento_id = f"stub-pay-{self._contador}"
        preferencia = self._preferencias[id_externo_preferencia]
        preferencia["status"] = "approved"
        preferencia["pagamento_id"] = pagamento_id
        return pagamento_id

    def buscar_pagamento(self, pagamento_id_externo: str) -> DetalhePagamento:
        for preferencia in self._preferencias.values():
            if preferencia["pagamento_id"] == pagamento_id_externo:
                return DetalhePagamento(
                    id_externo=pagamento_id_externo,
                    referencia_externa=preferencia["referencia_externa"],
                    status=preferencia["status"],
                    valor=preferencia["valor"],
                )
        raise NaoEncontrado(f"Pagamento {pagamento_id_externo} não encontrado no stub")
