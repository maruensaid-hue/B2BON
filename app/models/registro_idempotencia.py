from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroIdempotencia(Base):
    """Resposta gravada de uma requisição com `Idempotency-Key` (Fase 3).

    Repetir a mesma chave com o mesmo corpo devolve a resposta original
    sem reexecutar; a mesma chave com corpo diferente é rejeitada (409)."""

    __tablename__ = "registro_idempotencia"
    __table_args__ = (UniqueConstraint("tenant_id", "chave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    chave: Mapped[str] = mapped_column(String)
    rota: Mapped[str] = mapped_column(String)
    hash_corpo: Mapped[str] = mapped_column(String)
    status_code: Mapped[int] = mapped_column(Integer)
    resposta: Mapped[dict | list] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
