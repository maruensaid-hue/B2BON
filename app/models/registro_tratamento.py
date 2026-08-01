from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroTratamento(Base):
    """ROPA — Registro de Operações de Tratamento (E9-H1).

    Escopo de módulo/plataforma: um registro versionado por tipo de
    tratamento realizado pelo PREDATOR, mantido pelo Admin B2B ON — não por
    tenant, já que documenta as operações do próprio módulo perante a ANPD.
    """

    __tablename__ = "registro_tratamento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo_tratamento: Mapped[str] = mapped_column(String, index=True)
    finalidade: Mapped[str] = mapped_column(String)
    base_legal: Mapped[str] = mapped_column(String, default="legitimo_interesse")
    dados_tratados: Mapped[list] = mapped_column(JSON, default=list)
    balanceamento_documentado: Mapped[str] = mapped_column(String)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
