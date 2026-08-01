from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Oferta(Base):
    __tablename__ = "oferta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    icp_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(String)
    diferenciais: Mapped[list] = mapped_column(JSON, default=list)
    provas_sociais: Mapped[list] = mapped_column(JSON, default=list)
    faixa_preco_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    faixa_preco_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
