from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroSupressaoPermanente(Base):
    """Eliminação com preservação apenas do registro mínimo de supressão
    (E9-H3) — guarda só o hash do identificador, nunca o dado pessoal cru,
    para impedir recontato futuro do mesmo titular."""

    __tablename__ = "registro_supressao_permanente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    identificador_hash: Mapped[str] = mapped_column(String, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
