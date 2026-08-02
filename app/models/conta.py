from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conta(Base):
    __tablename__ = "conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    icp_id: Mapped[int] = mapped_column(ForeignKey("icp.id"))
    cnpj: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    nome: Mapped[str] = mapped_column(String)
    dominio: Mapped[str | None] = mapped_column(String, nullable=True)
    porte: Mapped[str | None] = mapped_column(String, nullable=True)
    segmento: Mapped[str | None] = mapped_column(String, nullable=True)
    regiao: Mapped[str | None] = mapped_column(String, nullable=True)
    score_aderencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String)  # prospectada | priorizada | descartada
    motivo_descarte: Mapped[str | None] = mapped_column(String, nullable=True)
    origem: Mapped[str | None] = mapped_column(String, nullable=True)
    # Classificação da última pesquisa de NPS respondida (E11-H1).
    nps_classificacao: Mapped[str | None] = mapped_column(String, nullable=True)  # promotor | neutro | detrator
    nps_nota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    neo4j_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
