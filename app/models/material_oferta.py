from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaterialOferta(Base):
    __tablename__ = "material_oferta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey("oferta.id"))
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    caminho: Mapped[str] = mapped_column(String)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
