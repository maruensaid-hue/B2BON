from app.providers.payout.base import PayoutProvider, ResultadoPayout


class StubPayoutProvider(PayoutProvider):
    """Dev/teste e modo simulação (`settings.payout_modo_simulacao`) —
    sempre reporta sucesso, nunca move dinheiro de verdade."""

    def enviar_pix(self, chave_pix: str, valor: float, referencia_externa: str, descricao: str) -> ResultadoPayout:
        return ResultadoPayout(sucesso=True, id_externo=f"stub-{referencia_externa}")
