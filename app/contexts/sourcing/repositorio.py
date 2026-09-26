"""Repositório por lado (S2, D-055 · `18_STRATEGIC_SOURCING.md` §2.3).

Contrato que cada lado implementa com o lado **fixo**: o lado vendedor só
recebe `RepositorioVenda` (em `bids`), o comprador só `RepositorioCompra`
(em `procurement`). Quem está fora de um lado lê pelo repositório desse lado,
nunca pelas tabelas. Hoje cada repositório lê as tabelas do próprio lado;
na S3 as duas implementações passam a ler as tabelas `*_sourcing` com
`side` fixo, sem que os chamadores mudem. A fitness function
`tests/unit/test_barreira_sourcing.py` garante a regra.
"""

from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.contexts.shared.paginacao import Pagina
from app.contexts.sourcing.tipos import Lado


@runtime_checkable
class RepositorioSourcing(Protocol):
    lado: Lado

    def listar_processos(self, db: Session, tenant_id: str, cursor: str | None = None, limite: int | None = None,
                         **filtros) -> Pagina: ...

    def obter_processo(self, db: Session, tenant_id: str, processo_id: int): ...

    def documentos(self, db: Session, tenant_id: str, processo_id: int) -> list:
        """Documentos do processo, sem o arquivo nem o texto (colunas deferidas)."""
        ...

    def tipos_de_documento(self, db: Session, tenant_id: str) -> dict[int, set[str]]:
        """processo_id → tipos de documento presentes, numa consulta."""
        ...
