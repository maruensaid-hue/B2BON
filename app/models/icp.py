from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ICP(Base):
    __tablename__ = "icp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    grupo_id: Mapped[str] = mapped_column(String, index=True)
    clonado_de_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    segmento: Mapped[str] = mapped_column(String)
    porte: Mapped[str] = mapped_column(String)
    regiao: Mapped[str] = mapped_column(String)
    dores: Mapped[list] = mapped_column(JSON, default=list)
    gatilhos: Mapped[list] = mapped_column(JSON, default=list)
    cnae_codigos: Mapped[list] = mapped_column(JSON, default=list)
    ufs: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
