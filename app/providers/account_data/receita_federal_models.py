from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CnpjEstabelecimento(Base):
    """Staging local do recorte carregado da base pública de CNPJ.

    Populado só com o recorte exigido pelos ICPs ativos (CNAE+UF na carga) —
    nunca a base completa (Seção 11 da especificação).
    """

    __tablename__ = "cnpj_estabelecimento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj: Mapped[str] = mapped_column(String, unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String)
    nome_fantasia: Mapped[str | None] = mapped_column(String, nullable=True)
    cnae_principal: Mapped[str] = mapped_column(String, index=True)
    porte: Mapped[str | None] = mapped_column(String, nullable=True)
    capital_social: Mapped[float | None] = mapped_column(Float, nullable=True)
    uf: Mapped[str] = mapped_column(String, index=True)
    municipio: Mapped[str | None] = mapped_column(String, nullable=True)
    situacao_cadastral: Mapped[str] = mapped_column(String)
    data_abertura: Mapped[str | None] = mapped_column(String, nullable=True)
    carregado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CnpjSocio(Base):
    """QSA (quadro societário) do recorte carregado — fonte de decisores."""

    __tablename__ = "cnpj_socio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj_basico: Mapped[str] = mapped_column(String, index=True)
    nome_socio: Mapped[str] = mapped_column(String)
    qualificacao: Mapped[str] = mapped_column(String)
    carregado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
