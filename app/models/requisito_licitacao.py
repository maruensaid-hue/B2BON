from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RequisitoLicitacao(Base):
    """Requisito extraído de um documento (Tender/TR Analyzer, §33-§34).
    
    Origem IA: nasce `sugerido`, com a evidência literal do documento; a
    página é calculada pelo sistema a partir do texto (não confiada à IA).
    Um humano confirma ou descarta, e pode sobrescrever a conformidade."""

    __tablename__ = "requisito_licitacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    licitacao_id: Mapped[int] = mapped_column(ForeignKey("licitacao.id"), index=True)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documento_licitacao.id"), nullable=True)
    categoria: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(String)
    evidencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    pagina: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clausula: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase B: obrigatório pela linguagem do trecho; None = UNKNOWN (sem sinal ou anterior à Phase B)
    obrigatorio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Phase C: resposta do fornecedor (pergunta de RFI/questionário, ou texto do requisito na proposta)
    resposta: Mapped[str | None] = mapped_column(Text, nullable=True)
    origem: Mapped[str] = mapped_column(String)  # ia | manual
    status: Mapped[str] = mapped_column(String)  # sugerido | confirmado | descartado
    conformidade_manual: Mapped[str | None] = mapped_column(String, nullable=True)
    justificativa_manual: Mapped[str | None] = mapped_column(String, nullable=True)
    revisado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
