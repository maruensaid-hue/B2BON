from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentoRi(Base):
    """Documento público de Relações com Investidores (relatório, resultado trimestral, demonstrações...) de uma conta (V5.2.1, Fase 5).

    **Não guarda o arquivo**: só o hash (idempotência: o mesmo PDF na mesma conta não duplica), metadados e as evidências extraídas. O PDF é lido em
    subprocesso isolado, com limite de tempo, memória e páginas, e o texto extraído é dado não confiável (nunca instrução)."""

    __tablename__ = "documento_ri"
    __table_args__ = (UniqueConstraint("tenant_id", "conta_id", "sha256", name="uq_documento_ri_tenant_conta_sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    origem: Mapped[str] = mapped_column(String)  # upload | url
    nome_arquivo: Mapped[str] = mapped_column(String)
    url_fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    paginas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_documento: Mapped[str] = mapped_column(String, default="outro")
    titulo: Mapped[str | None] = mapped_column(String, nullable=True)
    data_publicacao: Mapped[date | None] = mapped_column(Date, nullable=True)  # informada por quem enviou; nunca inferida do PDF
    estado: Mapped[str] = mapped_column(String)  # processado | sem_dados_financeiros | falhou
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)  # texto controlado, sem caminho nem credencial
    avisos: Mapped[list] = mapped_column(JSON, default=list)
    sinais: Mapped[list] = mapped_column(JSON, default=list)  # [{tipo, pagina, trecho}] — expansão, aquisição, investimento (qualitativos)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IndicadorRi(Base):
    """Indicador financeiro lido de um documento de RI, com a proveniência completa (documento, página, trecho, método, estado de validação)."""

    __tablename__ = "indicador_ri"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documento_ri.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String)
    tipo: Mapped[str] = mapped_column(String, default="publicado")  # publicado | derivado
    valor: Mapped[float] = mapped_column(Float)
    moeda: Mapped[str] = mapped_column(String)  # BRL | USD | %  (nunca convertida)
    escala: Mapped[str] = mapped_column(String)
    valor_original: Mapped[str] = mapped_column(String)  # como estava escrito
    periodo: Mapped[str | None] = mapped_column(String, nullable=True)
    pagina: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trecho: Mapped[str] = mapped_column(Text)
    metodo_extracao: Mapped[str] = mapped_column(String)
    confianca: Mapped[str] = mapped_column(String)  # alta | baixa
    estado_validacao: Mapped[str] = mapped_column(String, default="extraido_automaticamente")  # | conferido_manualmente | conflitante | rejeitado
    formula: Mapped[str | None] = mapped_column(String, nullable=True)
    origens: Mapped[list] = mapped_column(JSON, default=list)
    observacao: Mapped[str | None] = mapped_column(String, nullable=True)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
