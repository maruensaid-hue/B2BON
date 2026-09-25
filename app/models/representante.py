from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Representante(Base):
    """Vendedor externo (pessoa física) que vende o B2B ON e recebe uma
    comissão recorrente simples sobre a mensalidade de cada tenant que
    trouxe — conceito novo e cross-tenant, distinto da hierarquia de
    Distribuidor/Revendedor (`Tenant.modo_cobranca`/`tenant_pai_id`), que é
    sobre revenda estrutural entre empresas, não sobre uma pessoa
    recebendo comissão. Cadastrado só por super_admin."""

    __tablename__ = "representante"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    cpf: Mapped[str | None] = mapped_column(String, nullable=True)
    chave_pix: Mapped[str] = mapped_column(String)
    # Fração de 0 a 1 (0.10 = 10%) sobre o valor de cada `PagamentoLicenca`
    # aprovado de um tenant que tem este representante como
    # `Tenant.representante_id`.
    percentual_comissao: Mapped[float] = mapped_column(Float)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
