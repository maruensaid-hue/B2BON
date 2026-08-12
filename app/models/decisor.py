from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Decisor(Base):
    __tablename__ = "decisor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    nome: Mapped[str] = mapped_column(String)
    cargo: Mapped[str | None] = mapped_column(String, nullable=True)
    canal_provavel: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    telefone: Mapped[str | None] = mapped_column(String, nullable=True)
    neo4j_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # De onde veio este decisor (ex.: "receita_federal_cnpj_qsa",
    # "enriquecimento_contatos", "manual", "evento") — mesmo propósito de
    # Conta.origem, útil para explicar a procedência de cada contato.
    origem: Mapped[str | None] = mapped_column(String, nullable=True)
    # Janela de 24h do WhatsApp (E3-H2): última interação recebida do decisor.
    ultima_interacao_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Opt-out permanente (E9-H2): setado, bloqueia envio em qualquer canal/cadência.
    suprimido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
