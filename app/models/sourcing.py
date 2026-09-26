"""Tabelas unificadas de Strategic Sourcing & Bids (S3, D-055).

Expand do Strangler: as tabelas antigas (`licitacao`, `processo_contratacao`
e filhas) continuam a fonte da verdade; estas recebem uma cópia por espelho
(eventos do ORM) e backfill idempotente, e são comparadas na leitura dupla.

Regras de barreira (`18_STRATEGIC_SOURCING.md` §2.3):
- `lado` (SELL|BUY) em toda tabela, com CHECK, e **imutável** (evento do ORM
  aqui + trigger no banco, migração `a3d5f7b9c1e2`);
- só o núcleo `app/contexts/sourcing` importa este módulo (fitness);
- `origem_tabela` + `origem_id` = mapa id antigo → id novo, único.

O arquivo binário e o texto das páginas continuam na tabela de origem até a
S6 (não duplicar blobs no expand). Participantes, propostas, avaliações e
lotes/itens só ganham tabela quando o primeiro fluxo precisar (S7/S8).
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    DDL,
    UniqueConstraint,
    event,
    func,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LADOS = ("SELL", "BUY")
_CHECK_LADO = "lado IN ('SELL', 'BUY')"


class ProcessoSourcing(Base):
    __tablename__ = "processo_sourcing"
    __table_args__ = (
        UniqueConstraint("origem_tabela", "origem_id", name="uq_processo_sourcing_origem"),
        CheckConstraint(_CHECK_LADO, name="ck_processo_sourcing_lado"),
        CheckConstraint("segmento IN ('PUBLIC', 'ENTERPRISE')", name="ck_processo_sourcing_segmento"),
        Index("ix_processo_sourcing_tenant_lado_status", "tenant_id", "lado", "status"),
        Index("ix_processo_sourcing_tenant_lado_prazo", "tenant_id", "lado", "prazo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    segmento: Mapped[str] = mapped_column(String)
    tipo_processo: Mapped[str] = mapped_column(String)
    titulo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    emissor_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    emissor_cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True, index=True)
    oferta_id: Mapped[int | None] = mapped_column(ForeignKey("oferta.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String)
    visibilidade: Mapped[str] = mapped_column(String, default="PRIVADO")
    classificacao: Mapped[str] = mapped_column(String)
    ruleset: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow: Mapped[str] = mapped_column(String)
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prazo: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_estimado: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    moeda: Mapped[str] = mapped_column(String, default="BRL")
    valor_sigiloso: Mapped[bool] = mapped_column(Boolean, default=False)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fonte: Mapped[str] = mapped_column(String)
    fonte_id_externo: Mapped[str | None] = mapped_column(String, nullable=True)
    fonte_url: Mapped[str | None] = mapped_column(String, nullable=True)
    metadados: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    origem_tabela: Mapped[str] = mapped_column(String)
    origem_id: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    espelhado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContratoSourcing(Base):
    __tablename__ = "contrato_sourcing"
    __table_args__ = (
        UniqueConstraint("origem_tabela", "origem_id", name="uq_contrato_sourcing_origem"),
        CheckConstraint(_CHECK_LADO, name="ck_contrato_sourcing_lado"),
        Index("ix_contrato_sourcing_tenant_lado_status", "tenant_id", "lado", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int | None] = mapped_column(ForeignKey("processo_sourcing.id"), nullable=True, index=True)
    contraparte_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True, index=True)
    fornecedor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # fornecedor do comprador (BUY)
    numero: Mapped[str | None] = mapped_column(String, nullable=True)
    objeto: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_inicial: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    valor_atual: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    renovavel: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    necessidade_continuada: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String)
    sla: Mapped[str | None] = mapped_column(Text, nullable=True)
    garantia: Mapped[str | None] = mapped_column(String, nullable=True)
    metadados: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    origem_tabela: Mapped[str] = mapped_column(String)
    origem_id: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    espelhado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentoSourcing(Base):
    __tablename__ = "documento_sourcing"
    __table_args__ = (
        UniqueConstraint("origem_tabela", "origem_id", name="uq_documento_sourcing_origem"),
        CheckConstraint(_CHECK_LADO, name="ck_documento_sourcing_lado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int | None] = mapped_column(ForeignKey("processo_sourcing.id"), nullable=True, index=True)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato_sourcing.id"), nullable=True, index=True)
    tipo_documento: Mapped[str] = mapped_column(String)
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    fonte: Mapped[str] = mapped_column(String)
    fonte_url: Mapped[str | None] = mapped_column(String, nullable=True)
    classificacao: Mapped[str] = mapped_column(String)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    status_extracao: Mapped[str] = mapped_column(String)
    analisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    origem_tabela: Mapped[str] = mapped_column(String)
    origem_id: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    espelhado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RequisitoSourcing(Base):
    __tablename__ = "requisito_sourcing"
    __table_args__ = (
        UniqueConstraint("origem_tabela", "origem_id", "origem_indice", name="uq_requisito_sourcing_origem"),
        CheckConstraint(_CHECK_LADO, name="ck_requisito_sourcing_lado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int | None] = mapped_column(ForeignKey("processo_sourcing.id"), nullable=True, index=True)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documento_sourcing.id"), nullable=True, index=True)
    categoria: Mapped[str] = mapped_column(String)
    texto: Mapped[str] = mapped_column(Text)
    fonte: Mapped[str] = mapped_column(String)  # AI | MANUAL
    pagina: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clausula: Mapped[str | None] = mapped_column(String, nullable=True)
    trecho: Mapped[str | None] = mapped_column(Text, nullable=True)
    obrigatorio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = UNKNOWN
    resposta: Mapped[str | None] = mapped_column(Text, nullable=True)  # resposta de quem responde ao processo
    peso: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)  # critério ponderado (Phase E); None = peso 1
    confianca: Mapped[str] = mapped_column(String)  # grounded | manual
    status_revisao: Mapped[str] = mapped_column(String)  # sugerido | confirmado | descartado
    conformidade_manual: Mapped[str | None] = mapped_column(String, nullable=True)
    justificativa_manual: Mapped[str | None] = mapped_column(String, nullable=True)
    revisado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    origem_tabela: Mapped[str] = mapped_column(String)
    origem_id: Mapped[int] = mapped_column(Integer)
    origem_indice: Mapped[int] = mapped_column(Integer, default=0)  # posição no JSON de achados (BUY); 0 para tabela
    criado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    espelhado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EventoSourcing(Base):
    """Tarefa, prazo, esclarecimento, aprovação, marco e nota do processo."""

    __tablename__ = "evento_sourcing"
    __table_args__ = (
        UniqueConstraint("origem_tabela", "origem_id", name="uq_evento_sourcing_origem"),
        CheckConstraint(_CHECK_LADO, name="ck_evento_sourcing_lado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int | None] = mapped_column(ForeignKey("processo_sourcing.id"), nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    origem_tabela: Mapped[str] = mapped_column(String)
    origem_id: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    espelhado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EventoContratoSourcing(Base):
    """Aditivo, entrega, fiscalização, pagamento, ocorrência, renovação."""

    __tablename__ = "evento_contrato_sourcing"
    __table_args__ = (
        UniqueConstraint("origem_tabela", "origem_id", name="uq_evento_contrato_sourcing_origem"),
        CheckConstraint(_CHECK_LADO, name="ck_evento_contrato_sourcing_lado"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato_sourcing.id"), nullable=True, index=True)
    fornecedor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    nota: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    origem_tabela: Mapped[str] = mapped_column(String)
    origem_id: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    espelhado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- Phase E: entidades que nascem com o primeiro fluxo que grava nelas (D-058/D-061) --------------------
# Sem tabela de origem: são nativas do modelo unificado (Enterprise Strategic Sourcing).


class ParticipanteSourcing(Base):
    """Fornecedor convidado/descoberto para um processo (quem responde)."""

    __tablename__ = "participante_sourcing"
    __table_args__ = (CheckConstraint(_CHECK_LADO, name="ck_participante_sourcing_lado"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int] = mapped_column(ForeignKey("processo_sourcing.id"), index=True)
    fornecedor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # cadastro interno do comprador
    empresa_rede_tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)  # empresa da Business Network
    nome: Mapped[str] = mapped_column(String)
    cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    origem_descoberta: Mapped[str] = mapped_column(String)  # INTERNAL | NETWORK | MANUAL
    status: Mapped[str] = mapped_column(String)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ItemSourcing(Base):
    """Item cotado (RFQ): quantidade e especificação."""

    __tablename__ = "item_sourcing"
    __table_args__ = (CheckConstraint(_CHECK_LADO, name="ck_item_sourcing_lado"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int] = mapped_column(ForeignKey("processo_sourcing.id"), index=True)
    descricao: Mapped[str] = mapped_column(String)
    quantidade: Mapped[float] = mapped_column(Numeric(18, 4))
    unidade: Mapped[str | None] = mapped_column(String, nullable=True)
    especificacao: Mapped[str | None] = mapped_column(Text, nullable=True)


class PropostaSourcing(Base):
    """Resposta (RFI) ou proposta (RFP/RFQ) de um participante; cada rodada de negociação é uma nova linha."""

    __tablename__ = "proposta_sourcing"
    __table_args__ = (
        CheckConstraint(_CHECK_LADO, name="ck_proposta_sourcing_lado"),
        Index("ix_proposta_sourcing_processo_participante", "processo_id", "participante_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    processo_id: Mapped[int] = mapped_column(ForeignKey("processo_sourcing.id"))
    participante_id: Mapped[int] = mapped_column(ForeignKey("participante_sourcing.id"), index=True)
    rodada: Mapped[int] = mapped_column(Integer, default=1)
    tipo: Mapped[str] = mapped_column(String)  # RESPOSTA | PROPOSTA
    valor_total: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    moeda: Mapped[str] = mapped_column(String, default="BRL")
    prazo_entrega_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condicoes_pagamento: Mapped[str | None] = mapped_column(String, nullable=True)
    impostos_inclusos: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    recebida_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PropostaItemSourcing(Base):
    __tablename__ = "proposta_item_sourcing"
    __table_args__ = (
        CheckConstraint(_CHECK_LADO, name="ck_proposta_item_sourcing_lado"),
        UniqueConstraint("proposta_id", "item_id", name="uq_proposta_item_sourcing"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    proposta_id: Mapped[int] = mapped_column(ForeignKey("proposta_sourcing.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item_sourcing.id"), index=True)
    preco_unitario: Mapped[float] = mapped_column(Numeric(18, 4))


class AvaliacaoSourcing(Base):
    """Proposta × requisito: o que o participante respondeu e como o comprador avaliou (Evaluation Engine, direção PROPOSTA)."""

    __tablename__ = "avaliacao_sourcing"
    __table_args__ = (
        CheckConstraint(_CHECK_LADO, name="ck_avaliacao_sourcing_lado"),
        UniqueConstraint("proposta_id", "requisito_id", name="uq_avaliacao_sourcing"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    lado: Mapped[str] = mapped_column(String)
    proposta_id: Mapped[int] = mapped_column(ForeignKey("proposta_sourcing.id"), index=True)
    requisito_id: Mapped[int] = mapped_column(ForeignKey("requisito_sourcing.id"), index=True)
    resposta: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # STATUS_CONFORMIDADE; None = não avaliado
    nota: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # 0–10
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    revisado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


TABELAS_NATIVAS = (ParticipanteSourcing, ItemSourcing, PropostaSourcing, PropostaItemSourcing, AvaliacaoSourcing)
TABELAS_SOURCING = (ProcessoSourcing, ContratoSourcing, DocumentoSourcing, RequisitoSourcing, EventoSourcing, EventoContratoSourcing,
                    *TABELAS_NATIVAS)


class LadoImutavel(Exception):
    """`lado` de um registro de sourcing nunca muda (barreira Buy/Sell)."""


def _lado_imutavel(mapper, connection, alvo) -> None:
    historico = inspect(alvo).attrs.lado.history
    if historico.deleted and historico.deleted[0] is not None and historico.added and historico.added[0] != historico.deleted[0]:
        raise LadoImutavel(f"{alvo.__tablename__}.lado não pode mudar ({historico.deleted[0]} → {historico.added[0]}).")


for _modelo in TABELAS_SOURCING:
    event.listen(_modelo, "before_update", _lado_imutavel)


# Trigger de banco: o lado não muda nem por SQL direto. A migração
# `a3d5f7b9c1e2` cria os mesmos triggers; estes cobrem `create_all` (testes).
FUNCAO_PG = """
CREATE OR REPLACE FUNCTION sourcing_lado_imutavel() RETURNS trigger AS $$
BEGIN
    IF NEW.lado IS DISTINCT FROM OLD.lado THEN
        RAISE EXCEPTION USING MESSAGE = 'lado de ' || TG_TABLE_NAME || ' nao pode mudar';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def ddl_trigger_sqlite(tabela: str) -> str:
    return (f"CREATE TRIGGER trg_{tabela}_lado_imutavel BEFORE UPDATE OF lado ON {tabela} "
            f"WHEN NEW.lado <> OLD.lado BEGIN SELECT RAISE(ABORT, 'lado de {tabela} nao pode mudar'); END")


def ddl_trigger_pg(tabela: str) -> str:
    return (f"CREATE TRIGGER trg_{tabela}_lado_imutavel BEFORE UPDATE ON {tabela} "
            f"FOR EACH ROW EXECUTE FUNCTION sourcing_lado_imutavel()")


for _modelo in TABELAS_SOURCING:
    _tabela = _modelo.__table__
    event.listen(_tabela, "after_create", DDL(ddl_trigger_sqlite(_tabela.name)).execute_if(dialect="sqlite"))
    event.listen(_tabela, "after_create", DDL(FUNCAO_PG).execute_if(dialect="postgresql"))
    event.listen(_tabela, "after_create", DDL(ddl_trigger_pg(_tabela.name)).execute_if(dialect="postgresql"))
