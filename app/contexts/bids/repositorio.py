"""RepositorioVenda (S2): leituras do lado vendedor com o lado fixo.

Único caminho para quem está fora de `bids` ler licitações, decisões de
Go/No-Go e contratos ganhos (FinOps, Analytics).

S3 (expand): as tabelas antigas continuam respondendo; cada leitura de
processo, documento e requisito é conferida com as tabelas unificadas
(`sourcing.paridade`, só lado SELL). A troca de fonte é a S6.

Phase J1 (preparação da S6): com `sourcing_leitura_fonte = UNIFICADA`, as leituras de listagem
(processos, documentos, requisitos, tipos de documento) vêm das tabelas unificadas no formato antigo.
`obter_processo` continua na tabela antiga: o registro devolvido é alterado por quem chama.
"""

from datetime import datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.contexts.shared import paginacao
from app.contexts.bids import espelho
from app.contexts.sourcing.contract import leitura, paridade
from app.contexts.sourcing.contract import tipos as tipos_sourcing
from app.models.contrato_venda_publica import ContratoVendaPublica
from app.models.decisao_go_no_go import DecisaoGoNoGo
from app.models.documento_licitacao import DocumentoLicitacao
from app.models.licitacao import Licitacao
from app.models.requisito_licitacao import RequisitoLicitacao
from app.services.errors import NaoEncontrado


class RepositorioVenda:
    lado = tipos_sourcing.Lado.VENDA

    def _conferir(self, db: Session, tenant_id: str, tabela: str, origem: str, objetos: list, mapear, contexto: str) -> None:
        if paridade.ativa() and objetos:
            esperados = {o.id: mapear(o) for o in objetos}
            paridade.verificar(paridade.comparar(db, tabela, self.lado, tenant_id, origem, esperados), f"venda.{contexto}")

    def listar_processos(self, db: Session, tenant_id: str, cursor: str | None = None, limite: int | None = None,
                         status: str | None = None) -> paginacao.Pagina[Licitacao]:
        """Prazo mais próximo primeiro (sem prazo no fim), depois id decrescente.
        Keyset: a posição é (prazo, id) da última linha."""
        quantidade = paginacao.limite(limite)
        if leitura.unificada():
            linhas = [espelho.licitacao_de(linha) for linha in leitura.processos_por_prazo(
                db, self.lado, tenant_id, "licitacao", quantidade, paginacao.decodificar(cursor), status)]
            return paginacao.fatiar(linhas, quantidade, lambda lic: {
                "prazo": lic.prazo_proposta.isoformat() if lic.prazo_proposta else None, "id": lic.id})
        consulta = db.query(Licitacao).filter_by(tenant_id=tenant_id)
        if status:
            consulta = consulta.filter_by(status=status)
        posicao = paginacao.decodificar(cursor)
        if posicao is not None:
            ultimo_id = int(posicao["id"])
            if posicao.get("prazo") is None:
                consulta = consulta.filter(Licitacao.prazo_proposta.is_(None), Licitacao.id < ultimo_id)
            else:
                prazo = datetime.fromisoformat(posicao["prazo"])
                consulta = consulta.filter(or_(
                    Licitacao.prazo_proposta.is_(None),
                    Licitacao.prazo_proposta > prazo,
                    and_(Licitacao.prazo_proposta == prazo, Licitacao.id < ultimo_id),
                ))
        linhas = consulta.order_by(Licitacao.prazo_proposta.is_(None), Licitacao.prazo_proposta, Licitacao.id.desc()).limit(
            quantidade + 1).all()
        self._conferir(db, tenant_id, "processo", "licitacao", linhas[:quantidade], espelho.processo, "listar_processos")
        return paginacao.fatiar(linhas, quantidade, lambda lic: {
            "prazo": lic.prazo_proposta.isoformat() if lic.prazo_proposta else None, "id": lic.id})

    def obter_processo(self, db: Session, tenant_id: str, processo_id: int) -> Licitacao:
        licitacao = db.query(Licitacao).filter_by(id=processo_id, tenant_id=tenant_id).one_or_none()
        if licitacao is None:
            raise NaoEncontrado(f"Licitação {processo_id} não encontrada")
        self._conferir(db, tenant_id, "processo", "licitacao", [licitacao], espelho.processo, "obter_processo")
        return licitacao

    def documentos(self, db: Session, tenant_id: str, processo_id: int) -> list[DocumentoLicitacao]:
        if leitura.unificada():
            return [espelho.documento_de(linha, processo_id)
                    for linha in leitura.filhas(db, "documento", self.lado, tenant_id, ("licitacao", processo_id), "documento_licitacao")]
        documentos = (db.query(DocumentoLicitacao).filter_by(tenant_id=tenant_id, licitacao_id=processo_id)
                      .order_by(DocumentoLicitacao.id).all())
        self._conferir(db, tenant_id, "documento", "documento_licitacao", documentos, espelho.documento, "documentos")
        return documentos

    def requisitos(self, db: Session, tenant_id: str, processo_id: int, incluir_descartados: bool = False) -> list[RequisitoLicitacao]:
        if leitura.unificada():
            linhas = [linha for linha in leitura.filhas(db, "requisito", self.lado, tenant_id, ("licitacao", processo_id),
                                                        "requisito_licitacao")
                      if incluir_descartados or linha["status_revisao"] != "descartado"]
            docs = leitura.origens(db, "documento", {linha["documento_id"] for linha in linhas if linha["documento_id"]})
            requisitos = [espelho.requisito_de(linha, processo_id, docs[linha["documento_id"]][1] if linha["documento_id"] else None)
                          for linha in linhas]
            # mesma ordem da consulta antiga (documento, página, id); vazio fica onde o banco o põe (SQLite primeiro, Postgres por último)
            vazio_por_ultimo = db.get_bind().dialect.name == "postgresql"
            return sorted(requisitos, key=lambda r: ((r.documento_id is None) == vazio_por_ultimo, r.documento_id or 0,
                                                     (r.pagina is None) == vazio_por_ultimo, r.pagina or 0, r.id))
        consulta = db.query(RequisitoLicitacao).filter_by(tenant_id=tenant_id, licitacao_id=processo_id)
        if not incluir_descartados:
            consulta = consulta.filter(RequisitoLicitacao.status != "descartado")
        requisitos = consulta.order_by(RequisitoLicitacao.documento_id, RequisitoLicitacao.pagina, RequisitoLicitacao.id).all()
        self._conferir(db, tenant_id, "requisito", "requisito_licitacao", requisitos, espelho.requisito, "requisitos")
        return requisitos

    def tipos_de_documento(self, db: Session, tenant_id: str) -> dict[int, set[str]]:
        if leitura.unificada():
            return paridade.tipos_de_documento(db, self.lado, tenant_id, "licitacao")
        resultado: dict[int, set[str]] = {}
        for processo_id, tipo in db.query(DocumentoLicitacao.licitacao_id, DocumentoLicitacao.tipo).filter(
                DocumentoLicitacao.tenant_id == tenant_id):
            resultado.setdefault(processo_id, set()).add(tipo)
        if paridade.ativa():
            novo = paridade.tipos_de_documento(db, self.lado, tenant_id, "licitacao")
            paridade.verificar([] if novo == resultado else [f"tipos de documento: {novo} != {resultado}"], "venda.tipos_de_documento")
        return resultado

    # --- Leituras para quem está fora do contexto (FinOps, Analytics) ---------------
    def contar_processos(self, db: Session, inicio: datetime, fim: datetime, tenant_id: str | None = None) -> int:
        """Licitações criadas no período; sem tenant = total da plataforma (só contagem)."""
        consulta = db.query(func.count(Licitacao.id)).filter(Licitacao.criado_em >= inicio, Licitacao.criado_em < fim)
        if tenant_id:
            consulta = consulta.filter(Licitacao.tenant_id == tenant_id)
        return consulta.scalar() or 0

    def processos_criados(self, db: Session, tenant_id: str, inicio: datetime, fim: datetime) -> list[Licitacao]:
        return db.query(Licitacao).filter(Licitacao.tenant_id == tenant_id, Licitacao.criado_em >= inicio,
                                          Licitacao.criado_em < fim).all()

    def decisoes_go_no_go(self, db: Session, tenant_id: str, inicio: datetime, fim: datetime) -> list[DecisaoGoNoGo]:
        return db.query(DecisaoGoNoGo).filter(DecisaoGoNoGo.tenant_id == tenant_id, DecisaoGoNoGo.criado_em >= inicio,
                                              DecisaoGoNoGo.criado_em < fim).all()

    def contratos_vigentes(self, db: Session, tenant_id: str) -> list[ContratoVendaPublica]:
        return db.query(ContratoVendaPublica).filter_by(tenant_id=tenant_id, status="VIGENTE").all()


VENDA = RepositorioVenda()
