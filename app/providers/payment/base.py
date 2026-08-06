from abc import ABC, abstractmethod

from pydantic import BaseModel


class PreferenciaCriada(BaseModel):
    id_externo: str
    url_checkout: str


class DetalhePagamento(BaseModel):
    id_externo: str
    referencia_externa: str | None
    status: str  # approved | pending | rejected | ... (vocabulário do provedor)
    valor: float


class PaymentProvider(ABC):
    """Porta de cobrança — cadastro self-service com escolha de plano
    (raio-X de produção). Único caminho de criação de cobrança permitido;
    a licença só ativa via `confirmar_via_webhook`, nunca direto pela
    resposta do checkout (o retorno do navegador não é confiável sozinho)."""

    @abstractmethod
    def criar_preferencia(
        self, referencia_externa: str, descricao: str, valor: float, email_pagador: str
    ) -> PreferenciaCriada:
        raise NotImplementedError

    @abstractmethod
    def buscar_pagamento(self, pagamento_id_externo: str) -> DetalhePagamento:
        raise NotImplementedError
