from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegraAprendida(Base):
    """Loop de aprendizado (master prompt, seções 13/14) — texto livre
    escrito por um humano depois de ver um padrão de edição/rejeição
    repetido, injetado automaticamente no prompt de geração de toques de
    cadência (raio-X 2026-09-17). `icp_id`/`oferta_id`/`canal` nulos
    aplicam a todos — mesmo raciocínio de nullable já usado em
    `Cadencia.icp_id`/`oferta_id`."""

    __tablename__ = "regra_aprendida"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    icp_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    oferta_id: Mapped[int | None] = mapped_column(ForeignKey("oferta.id"), nullable=True)
    canal: Mapped[str | None] = mapped_column(String, nullable=True)
    regra: Mapped[str] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
