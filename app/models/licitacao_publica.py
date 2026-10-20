from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LicitacaoPublica(Base):
    """Corpus público comum de licitações (V5.2.1, Fase 3): o FATO público de um edital, único por (fonte, id externo) em toda a plataforma.

    Contém somente o que a fonte publica (órgão, objeto, datas, valor, situação, link). **Não tem `tenant_id` de propósito**: score, anotação,
    estratégia, vínculo com conta/oferta, responsável e resultado são privados e vivem em `licitacao` (por tenant), que aponta para esta linha por
    `licitacao.corpus_id`. Nada privado deve ser adicionado aqui — um teste de esquema garante que a tabela não ganhe colunas de tenant.
    """

    __tablename__ = "licitacao_publica"
    __table_args__ = (UniqueConstraint("fonte", "fonte_id_externo", name="uq_licitacao_publica_fonte_id"),
                      Index("ix_licitacao_publica_uf_publicacao", "uf", "data_publicacao"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fonte: Mapped[str] = mapped_column(String)
    fonte_id_externo: Mapped[str] = mapped_column(String)
    titulo: Mapped[str] = mapped_column(String)
    objeto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    orgao_cnpj: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String, nullable=True)
    modalidade: Mapped[str] = mapped_column(String)
    modalidade_codigo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_publicacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prazo_proposta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    situacao_externa: Mapped[str | None] = mapped_column(String, nullable=True)
    atualizado_externo_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    # SHA-256 do conteúdo público normalizado: é o que separa "recoletei o mesmo edital" de "o edital foi retificado".
    hash_conteudo: Mapped[str] = mapped_column(String(64))
    versao: Mapped[int] = mapped_column(Integer, default=1)
    primeira_coleta_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultima_coleta_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultima_alteracao_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EventoLicitacaoPublica(Base):
    """Histórico de mudanças do edital NA FONTE (retificação, mudança de situação). Público, como a linha-mãe."""

    __tablename__ = "evento_licitacao_publica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    licitacao_publica_id: Mapped[int] = mapped_column(ForeignKey("licitacao_publica.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String)  # criada | retificada | situacao_alterada
    mudancas: Mapped[dict] = mapped_column(JSON, default=dict)  # {campo: [antes, depois]}
    versao: Mapped[int] = mapped_column(Integer)
    observado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
