from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Usuario(Base):
    """Usuário humano da plataforma B2B ON, autenticado por e-mail/senha
    ou Google (Onda A)."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    nome: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    senha_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    papel: Mapped[str] = mapped_column(String)  # super_admin | admin | user
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Registro do aceite de Política de Privacidade/Termos de Uso no
    # cadastro (LGPD) — nulo para quem foi criado antes deste campo
    # existir; todo cadastro novo passa a exigir e a gravar a data.
    termos_aceitos_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
