from abc import ABC, abstractmethod

from pydantic import BaseModel


class ResultadoPayout(BaseModel):
    sucesso: bool
    id_externo: str | None = None
    motivo_falha: str | None = None


class PayoutProvider(ABC):
    """Porta de repasse de comissão — envia dinheiro de verdade pro
    Representante (distinto de `PaymentProvider`, que só recebe pagamento
    de tenant via Checkout Pro). Nenhuma implementação real existia no
    projeto antes desta feature; a implementação de produção precisa ser
    escrita contra a documentação oficial vigente do produto de
    transferência Pix do Mercado Pago no momento em que for ligada de
    verdade — o formato exato do endpoint não deve ser assumido de
    memória, por mover dinheiro real."""

    @abstractmethod
    def enviar_pix(self, chave_pix: str, valor: float, referencia_externa: str, descricao: str) -> ResultadoPayout:
        raise NotImplementedError
