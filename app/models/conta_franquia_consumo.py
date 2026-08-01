from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContaFranquiaConsumo(Base):
    """Consumo de franquia por conta (E2-H1).

    A conta consome franquia ao ser incluída em uma cadência ativada — nunca
    na geração, avaliação ou descarte de listas. Único por
    tenant_id+conta_id+ano_mes: garante que a mesma conta, incluída mais de
    uma vez na mesma janela mensal, consome uma única vez.
    """

    __tablename__ = "conta_franquia_consumo"
    __table_args__ = (UniqueConstraint("tenant_id", "conta_id", "ano_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    ano_mes: Mapped[str] = mapped_column(String)  # "YYYY-MM"
    consumido_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
