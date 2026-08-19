from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChaveApiParceiro(Base):
    """Credencial de máquina (não humana) pra um Distribuidor chamar a API
    de provisionamento/billing de fora do painel (Fase 2 da hierarquia,
    raio-X). Só a `chave_hash` (SHA-256, não bcrypt — a chave já nasce de
    alta entropia via `secrets.token_urlsafe`, nunca é "adivinhada" como
    senha humana) fica no banco; a chave completa só existe uma vez, na
    resposta do POST que a cria."""

    __tablename__ = "chave_api_parceiro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    nome: Mapped[str] = mapped_column(String)
    prefixo: Mapped[str] = mapped_column(String)
    chave_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
