from app.providers.payout.base import PayoutProvider, ResultadoPayout


class MercadoPagoPayoutProvider(PayoutProvider):
    """Transferência Pix real pro Representante — **ainda não implementada**.

    `MercadoPagoProvider` (app/providers/payment/mercadopago.py) só cobre o
    Checkout Pro (RECEBER pagamento); não existe hoje, em nenhum lugar
    deste projeto, uma integração de envio de dinheiro. Antes de ligar
    isto de verdade em produção, é preciso:

    1. Confirmar contra a documentação oficial vigente do Mercado Pago
       qual produto/endpoint corresponde a "transferência Pix"/"Pix Out"
       pra essa conta especificamente (o endpoint e os campos exigidos
       não devem ser assumidos de memória — é uma chamada que move
       dinheiro real).
    2. Confirmar que o `access_token` configurado tem esse escopo
       habilitado (o token de Checkout Pro já usado em
       `mercadopago_access_token` pode não servir pra isso).
    3. Testar um único repasse de valor baixo manualmente antes de deixar
       o cron (`cron_repasse_comissoes_service`) rodar sozinho.

    Até isso acontecer, `settings.payout_modo_simulacao` deve continuar
    `True` em produção — `get_payout_provider` (app/api/deps.py) então usa
    `StubPayoutProvider`, nunca esta classe."""

    def enviar_pix(self, chave_pix: str, valor: float, referencia_externa: str, descricao: str) -> ResultadoPayout:
        raise NotImplementedError(
            "Repasse via Pix real ainda não implementado — ver docstring de MercadoPagoPayoutProvider. "
            "Mantenha settings.payout_modo_simulacao=True até esta integração estar pronta."
        )
