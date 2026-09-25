from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CATEGORIAS = ("dor", "requisito", "orcamento", "autoridade", "prazo", "concorrencia", "objecao", "outro")
STATUS = ("sugerida", "confirmada", "descartada")


class NecessidadeOportunidade(Base):
    """Necessidade do cliente numa oportunidade (master prompt §20-§23, Fase 6).

    `origem="ia"` nasce `sugerida`, com a citação literal da transcrição
    ou nota (checada contra o texto antes de gravar). Só um humano muda
    para `confirmada` ou `descartada`. `origem="manual"` já nasce
    confirmada: foi o vendedor quem registrou.
    """

    __tablename__ = "necessidade_oportunidade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocio.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    categoria: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(String)
    citacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    fonte_tipo: Mapped[str] = mapped_column(String)  # reuniao | atividade | manual
    fonte_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origem: Mapped[str] = mapped_column(String)  # ia | manual
    status: Mapped[str] = mapped_column(String)
    registro_uso_ia_correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    revisado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
