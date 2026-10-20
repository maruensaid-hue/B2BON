"""Porta das fontes públicas de licitação (§49).

O domínio não conhece a fonte: cada adapter devolve `LicitacaoExterna`
normalizada (com `fonte`, `id_externo` e `url`, a proveniência), e a
ingestão é idempotente por (tenant, fonte, id_externo).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LicitacaoExterna:
    fonte: str
    id_externo: str
    titulo: str
    objeto: str | None
    orgao_nome: str | None
    orgao_cnpj: str | None
    modalidade: str
    data_publicacao: datetime | None
    prazo_proposta: datetime | None
    valor_estimado: float | None
    url: str | None
    bruto: dict = field(default_factory=dict, compare=False)
    # Situação na fonte (PNCP: Divulgada, Revogada, Anulada, Suspensa) e quando a fonte atualizou o registro pela última vez:
    # é assim que cancelamento, suspensão e retificação de um edital já ingerido chegam ao produto.
    situacao_externa: str | None = field(default=None, compare=False)
    atualizado_externo_em: datetime | None = field(default=None, compare=False)
    # Localização do órgão e código da modalidade na fonte: base do filtro por região dos alertas e do corpus público.
    uf: str | None = field(default=None, compare=False)
    municipio: str | None = field(default=None, compare=False)
    modalidade_codigo: int | None = field(default=None, compare=False)


class FonteLicitacoes(ABC):
    nome: str
    status: str  # DISPONIVEL | EXPERIMENTAL | INDISPONIVEL

    @abstractmethod
    def buscar(self, data_inicial: str, data_final: str, modalidade: int | None = None, pagina: int = 1) -> list[LicitacaoExterna]:
        """Datas no formato AAAAMMDD."""
