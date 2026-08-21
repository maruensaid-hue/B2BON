from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConviteVitrine(Base):
    """Código de convite para uma empresa nova entrar na Rede Social sem
    virar cliente pagante (Onda H), ou — quando `gratuito=True` (raio-X)
    — para conceder o plano "Teste" sem passar pelo checkout, restrito a
    quem gera o convite ser admin/super_admin (ver
    `app/api/v1/convites.py`).

    Ao ser aceito, gera um `Tenant` + `Usuario` próprios; a `Licença`
    nasce `pendente_pagamento` (convite normal) ou `ativa` sem
    `data_expiracao` (convite gratuito) — é o status/ausência de licença
    ativa que restringe a conta, não um flag redundante aqui.
    """

    __tablename__ = "convite_vitrine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_origem: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    codigo: Mapped[str] = mapped_column(String, unique=True, index=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="disponivel")  # disponivel | usado | revogado | expirado
    validade_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tenant_id_gerado: Mapped[str | None] = mapped_column(ForeignKey("tenant.id"), nullable=True)
    gratuito: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
