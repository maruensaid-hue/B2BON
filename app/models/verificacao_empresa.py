from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VerificacaoEmpresa(Base):
    """Company Claim / Verification (master prompt §37, §63 Trust Layer,
    Fase 1B, raio-X 2026-09-17) — Trust Layer sobre o `PerfilEmpresa` que
    já existe (todo `Tenant` já é um participante ativo, não uma empresa
    pública "não reivindicada"): o tenant solicita, dois sinais são
    calculados automaticamente, e um super_admin decide de verdade
    (revisão manual — o master prompt exige múltiplos sinais + revisão
    manual, nunca aprovação 100% automática)."""

    __tablename__ = "verificacao_empresa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="pendente")  # pendente | aprovada | rejeitada
    email_verificacao: Mapped[str] = mapped_column(String)
    # Sinais automáticos — nunca decidem por si só, só orientam a revisão.
    dominio_confere: Mapped[bool] = mapped_column(Boolean, default=False)
    cnpj_encontrado_receita: Mapped[bool] = mapped_column(Boolean, default=False)
    solicitado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    solicitado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    revisado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_rejeicao: Mapped[str | None] = mapped_column(String, nullable=True)
