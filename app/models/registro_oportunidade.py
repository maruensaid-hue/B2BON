from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroOportunidade(Base):
    """Deal registration: um revendedor registra que descobriu uma
    oportunidade numa empresa (por CNPJ, podendo nem existir `Conta`
    cadastrada ainda) e fica PRIME dela dentro da própria rede de
    tenants (`tenant_service.tenant_ids_da_rede`). Só um RO `"ativo"` por
    CNPJ é permitido por rede — garantido pelo índice único parcial
    abaixo, não por uma checagem prévia em código (evita race condition
    entre dois revendedores registrando ao mesmo tempo)."""

    __tablename__ = "registro_oportunidade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    # Denormalizado na criação via `tenant_service.obter_raiz_da_rede` —
    # existe só pra viabilizar o índice único parcial (o conflito é por
    # rede, não por tenant exato).
    rede_raiz_tenant_id: Mapped[str] = mapped_column(String, index=True)
    vendedor_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    cnpj: Mapped[str] = mapped_column(String, index=True)
    nome_empresa: Mapped[str] = mapped_column(String)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    status: Mapped[str] = mapped_column(String)  # ativo | expirado | ganho | perdido | cancelado
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


Index(
    "ix_registro_oportunidade_ativo_unico",
    RegistroOportunidade.rede_raiz_tenant_id,
    RegistroOportunidade.cnpj,
    unique=True,
    postgresql_where=(RegistroOportunidade.status == "ativo"),
    sqlite_where=(RegistroOportunidade.status == "ativo"),
)
