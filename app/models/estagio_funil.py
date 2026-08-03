from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EstagioFunil(Base):
    """Catálogo de estágios do funil de vendas, configurável por tenant
    (Onda B — CRM Core), não hardcoded no código."""

    __tablename__ = "estagio_funil"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    ordem: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String)  # aberto | ganho | perdido
