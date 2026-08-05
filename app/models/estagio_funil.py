from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EstagioFunil(Base):
    """Catálogo de estágios do funil de vendas, configurável por tenant
    (Onda B — CRM Core), não hardcoded no código.

    UniqueConstraint(tenant_id, ordem): sem isso, duas chamadas concorrentes
    a `garantir_estagios_padrao` (ex.: duas abas abrindo o CRM ao mesmo
    tempo no primeiro uso) podiam ambas ver a tabela vazia e inserir o
    funil padrão duas vezes — bug real observado em produção.
    """

    __tablename__ = "estagio_funil"
    __table_args__ = (UniqueConstraint("tenant_id", "ordem"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    ordem: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String)  # aberto | ganho | perdido
