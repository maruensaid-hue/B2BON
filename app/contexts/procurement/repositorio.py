"""RepositorioCompra (S2): leituras do lado comprador com o lado fixo.

Só o próprio contexto de procurement e a API do comprador o usam (barreira
Buy/Sell, `tests/unit/test_barreira_sourcing.py`).

S3 (expand): as tabelas antigas continuam respondendo; cada leitura é
conferida com as tabelas unificadas (`sourcing.paridade`, só lado BUY),
incluindo os achados de documento como requisitos. A troca é a S6.
"""

from sqlalchemy.orm import Session

from app.contexts.procurement import cadastros, espelho
from app.contexts.shared import paginacao
from app.contexts.sourcing.contract import leitura, paridade
from app.contexts.sourcing.contract import tipos as tipos_sourcing
from app.models.documento_compras import DocumentoCompras
from app.models.processo_contratacao import ProcessoContratacao


class RepositorioCompra:
    lado = tipos_sourcing.Lado.COMPRA

    def _conferir(self, db: Session, tenant_id: str, tabela: str, origem: str, esperados: dict, contexto: str) -> None:
        if paridade.ativa() and esperados:
            paridade.verificar(paridade.comparar(db, tabela, self.lado, tenant_id, origem, esperados), f"compra.{contexto}")

    def listar_processos(self, db: Session, tenant_id: str, cursor: str | None = None, limite: int | None = None,
                         **filtros) -> paginacao.Pagina[ProcessoContratacao]:
        pagina = cadastros.listar(db, tenant_id, "processo_contratacao", cursor, limite, **filtros)
        self._conferir(db, tenant_id, "processo", "processo_contratacao", {p.id: espelho.processo(p) for p in pagina.itens},
                       "listar_processos")
        return pagina

    def obter_processo(self, db: Session, tenant_id: str, processo_id: int) -> ProcessoContratacao:
        processo = cadastros.obter(db, tenant_id, "processo_contratacao", processo_id)
        self._conferir(db, tenant_id, "processo", "processo_contratacao", {processo.id: espelho.processo(processo)}, "obter_processo")
        return processo

    def documentos(self, db: Session, tenant_id: str, processo_id: int) -> list[DocumentoCompras]:
        documentos = (db.query(DocumentoCompras).filter_by(tenant_id=tenant_id, processo_id=processo_id)
                      .order_by(DocumentoCompras.id).all())
        self._conferir(db, tenant_id, "documento", "documento_compras", {d.id: espelho.documento(d) for d in documentos}, "documentos")
        self._conferir(db, tenant_id, "requisito", espelho.ORIGEM_ACHADOS,
                       {d.id: espelho.requisitos_do_documento(d) for d in documentos}, "achados")
        return documentos

    def tipos_de_documento(self, db: Session, tenant_id: str) -> dict[int, set[str]]:
        if leitura.unificada():  # Phase J1: única leitura do comprador já trocável (processo e documentos: ver 18 §10)
            return paridade.tipos_de_documento(db, self.lado, tenant_id, "processo_contratacao")
        resultado: dict[int, set[str]] = {}
        for processo_id, tipo in db.query(DocumentoCompras.processo_id, DocumentoCompras.tipo).filter(
                DocumentoCompras.tenant_id == tenant_id, DocumentoCompras.processo_id.isnot(None)):
            resultado.setdefault(processo_id, set()).add(tipo)
        if paridade.ativa():
            novo = paridade.tipos_de_documento(db, self.lado, tenant_id, "processo_contratacao")
            paridade.verificar([] if novo == resultado else [f"tipos de documento: {novo} != {resultado}"], "compra.tipos_de_documento")
        return resultado


COMPRA = RepositorioCompra()
