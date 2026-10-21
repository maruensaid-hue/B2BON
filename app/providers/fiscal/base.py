"""Porta de emissão de nota fiscal das vendas (pacotes de créditos de enriquecimento).

A plataforma NÃO tem, hoje, nenhum emissor fiscal integrado (ver `docs/b2bon/OPEN_ISSUES.md`, OI-025): esta porta define o contrato e a emissão só acontece
quando um adaptador REAL for escolhido, configurado e implementado pelo responsável fiscal. Enquanto isso `FiscalDesativado` é o único adaptador de produção
(`disponivel = False`): nada é emitido, nada é simulado e o checkout de pacotes permanece bloqueado. O contrato deliberadamente NÃO calcula tributos: o
emissor aplica as regras fiscais da empresa; a plataforma só entrega os dados da venda."""

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel


class DadosNota(BaseModel):
    chave_idempotencia: str  # a mesma venda nunca gera duas notas, mesmo com nova tentativa
    compra_id: int
    tenant_id: str
    tomador_razao_social: str
    tomador_cnpj: str
    descricao: str
    valor_brl: Decimal


class NotaEmitida(BaseModel):
    numero: str
    referencia_externa: str
    chave_acesso: str | None = None
    url_documento: str | None = None


class FiscalIndisponivel(Exception):
    """Emissor fora do ar, não configurado ou sem credencial: pode tentar de novo depois."""


class FiscalRejeitou(Exception):
    """O emissor recusou os dados da venda: precisa de correção antes de nova tentativa."""


class FiscalProvider(ABC):
    nome: str = "fiscal"
    disponivel: bool = True

    @abstractmethod
    def emitir(self, dados: DadosNota) -> NotaEmitida:
        raise NotImplementedError
