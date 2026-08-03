from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustoAquisicao(Base):
    """Gasto de aquisição do período, informado manualmente pelo Gestor
    Comercial — único insumo para CAC que ainda não existe automatizado
    (Onda B)."""

    __tablename__ = "custo_aquisicao"
    __table_args__ = (UniqueConstraint("tenant_id", "periodo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    periodo: Mapped[str] = mapped_column(String)  # "YYYY-MM"
    valor: Mapped[float] = mapped_column(Float)
