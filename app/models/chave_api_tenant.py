from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChaveApiTenant(Base):
    """Chave de API de produto por tenant (Fase 3, Master Prompt §11/§64).

    Diferente de `ChaveApiParceiro` (provisionamento de Distribuidor): esta
    dá acesso às APIs de produto (`/api/v1/map/*`, `/api/v1/predator/*`)
    dentro dos `escopos` concedidos. Só o hash SHA-256 fica gravado; o
    segredo aparece uma única vez, na criação."""

    __tablename__ = "chave_api_tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    nome: Mapped[str] = mapped_column(String)
    prefixo: Mapped[str] = mapped_column(String)
    chave_hash: Mapped[str] = mapped_column(String, unique=True)
    escopos: Mapped[list] = mapped_column(JSON, default=list)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
