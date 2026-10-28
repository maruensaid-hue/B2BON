from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BloqueioContato(Base):
    """Lista de bloqueio da empresa: e-mail e/ou telefone de quem pediu para não receber mais nada, valendo para todas as campanhas (inclusive as coladas, sem cadastro
    de contato por trás). Antes, o cancelamento de um destinatário colado só valia dentro da campanha em que ele estava.

    `email` fica em minúsculas e `telefone` só com dígitos; pelo menos um dos dois existe. Quem libera um bloqueio (`DELETE`) é sempre uma pessoa da própria empresa."""

    __tablename__ = "bloqueio_contato"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    telefone: Mapped[str | None] = mapped_column(String, nullable=True)
    motivo: Mapped[str] = mapped_column(String)
    origem: Mapped[str] = mapped_column(String)  # campanha | manual
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
