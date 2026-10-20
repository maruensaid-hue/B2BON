from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoColetaFonte(Base):
    """O que a coleta agendada de uma fonte pública (hoje só PNCP) busca para o tenant.

    Desligada por padrão e sempre filtrada: ingerir todas as contratações do país (milhares por dia) estouraria o banco.
    Sem `ufs` nem `palavras_chave` a configuração não pode ser ativada."""

    __tablename__ = "configuracao_coleta_fonte"
    __table_args__ = (UniqueConstraint("tenant_id", "fonte", name="uq_configuracao_coleta_fonte_tenant_fonte"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    fonte: Mapped[str] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    modalidades: Mapped[list] = mapped_column(JSON, default=list)  # códigos do PNCP (1..19)
    ufs: Mapped[list] = mapped_column(JSON, default=list)  # filtra no servidor (um pedido por UF)
    palavras_chave: Mapped[list] = mapped_column(JSON, default=list)  # filtra no objeto da contratação
    janela_dias: Mapped[int] = mapped_column(Integer, default=2, server_default="2")  # primeira coleta e piso do overlap
    max_novas_por_execucao: Mapped[int] = mapped_column(Integer, default=200, server_default="200")
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ExecucaoColetaFonte(Base):
    """Uma execução da coleta (agendada ou manual): estado, contadores e o ponto de referência para retomar."""

    __tablename__ = "execucao_coleta_fonte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    fonte: Mapped[str] = mapped_column(String)
    disparo: Mapped[str] = mapped_column(String, default="agendado")  # agendado | manual
    # em_andamento | concluida | parcial (teto da execução atingido) | falhou
    estado: Mapped[str] = mapped_column(String, default="em_andamento")
    iniciada_em: Mapped[datetime] = mapped_column(DateTime)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duracao_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consultados: Mapped[int] = mapped_column(Integer, default=0)
    inseridos: Mapped[int] = mapped_column(Integer, default=0)
    atualizados: Mapped[int] = mapped_column(Integer, default=0)
    ignorados: Mapped[int] = mapped_column(Integer, default=0)
    # Registros já ingeridos que a fonte alterou (retificação) ou cuja situação mudou (anulada, revogada, suspensa).
    alterados_na_fonte: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)  # chamadas HTTP à fonte, somadas
    erro: Mapped[str | None] = mapped_column(String, nullable=True)
    data_inicial: Mapped[str | None] = mapped_column(String, nullable=True)  # AAAAMMDD da janela consultada
    data_final: Mapped[str | None] = mapped_column(String, nullable=True)
    # AAAAMMDD até onde a coleta está completa. Só avança em execução `concluida`; falha/parcial repete a janela (idempotente).
    cursor_referencia: Mapped[str | None] = mapped_column(String, nullable=True)


# No máximo uma execução em andamento por tenant e fonte: duas ao mesmo tempo (cron sobreposto, clique duplo) não passam.
Index(
    "ix_execucao_coleta_fonte_uma_em_andamento",
    ExecucaoColetaFonte.tenant_id,
    ExecucaoColetaFonte.fonte,
    unique=True,
    postgresql_where=(ExecucaoColetaFonte.estado == "em_andamento"),
    sqlite_where=(ExecucaoColetaFonte.estado == "em_andamento"),
)
