from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConviteVitrine(Base):
    """Código de convite para uma empresa nova entrar na Rede Social sem
    virar cliente pagante (Onda H).

    Ao ser aceito, gera um `Tenant` + `Usuario` próprios, sem `Licença` —
    é a ausência de licença ativa que restringe a conta só à Rede Social
    (`deps.exigir_licenca_ativa`), não um flag redundante aqui.
    """

    __tablename__ = "convite_vitrine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_origem: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    codigo: Mapped[str] = mapped_column(String, unique=True, index=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="disponivel")  # disponivel | usado | revogado | expirado
    validade_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id_gerado: Mapped[str | None] = mapped_column(ForeignKey("tenant.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
