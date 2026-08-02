from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tenant(Base):
    """Registro autoritativo de assinante da B2B ON (Onda A — Núcleo).

    `id` é o mesmo slug já usado como `tenant_id` em todas as tabelas do
    PREDATOR (ex. "cyberfort") — nenhuma tabela existente ganha FK formal
    para esta, para não tocar em dezenas de modelos sem necessidade; este
    registro é a fonte de verdade de quais tenant_id são válidos.
    """

    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    razao_social: Mapped[str] = mapped_column(String)
    cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
