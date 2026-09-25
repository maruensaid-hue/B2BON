from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FornecedorCompras(Base):
    """Fornecedor no cadastro do comprador (Supplier 360, §42). Dados oficiais, internos e autodeclarados ficam separados.

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "fornecedor_compras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    razao_social: Mapped[str] = mapped_column(String)
    categorias: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dados_oficiais: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dados_internos: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
