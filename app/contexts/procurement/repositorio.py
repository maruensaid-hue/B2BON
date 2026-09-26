"""RepositorioCompra (S2): leituras do lado comprador com o lado fixo.

Só o próprio contexto de procurement e a API do comprador o usam (barreira
Buy/Sell, `tests/unit/test_barreira_sourcing.py`). Na S3 passa a ler
`processo_sourcing` com `side = BUY`.
"""

from sqlalchemy.orm import Session

from app.contexts.procurement import cadastros
from app.contexts.shared import paginacao
from app.contexts.sourcing.contract import tipos as tipos_sourcing
from app.models.documento_compras import DocumentoCompras
from app.models.processo_contratacao import ProcessoContratacao


class RepositorioCompra:
    lado = tipos_sourcing.Lado.COMPRA

    def listar_processos(self, db: Session, tenant_id: str, cursor: str | None = None, limite: int | None = None,
                         **filtros) -> paginacao.Pagina[ProcessoContratacao]:
        return cadastros.listar(db, tenant_id, "processo_contratacao", cursor, limite, **filtros)

    def obter_processo(self, db: Session, tenant_id: str, processo_id: int) -> ProcessoContratacao:
        return cadastros.obter(db, tenant_id, "processo_contratacao", processo_id)

    def documentos(self, db: Session, tenant_id: str, processo_id: int) -> list[DocumentoCompras]:
        return (db.query(DocumentoCompras).filter_by(tenant_id=tenant_id, processo_id=processo_id)
                .order_by(DocumentoCompras.id).all())

    def tipos_de_documento(self, db: Session, tenant_id: str) -> dict[int, set[str]]:
        resultado: dict[int, set[str]] = {}
        for processo_id, tipo in db.query(DocumentoCompras.processo_id, DocumentoCompras.tipo).filter(
                DocumentoCompras.tenant_id == tenant_id, DocumentoCompras.processo_id.isnot(None)):
            resultado.setdefault(processo_id, set()).add(tipo)
        return resultado


COMPRA = RepositorioCompra()
