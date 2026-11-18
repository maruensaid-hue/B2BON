from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotaDaily(Base):
    """Anotação da daily do gestor no MAP (pedido do PO em 18/11/2026).

    O gestor escreve hoje e a nota volta em destaque no MAP em `exibir_em` (padrão: o dia seguinte, data de Brasília). Continua em destaque nos dias
    seguintes até ele marcar como vista (`concluida_em`), para não se perder num fim de semana ou feriado. A nota é PRIVADA de quem escreveu: outro gestor do
    mesmo tenant não a vê (decisão registrada no CHANGELOG — a daily é o caderno pessoal do gestor, não um mural do time).
    """

    __tablename__ = "nota_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    autor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    texto: Mapped[str] = mapped_column(Text)
    exibir_em: Mapped[date] = mapped_column(Date, index=True)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
