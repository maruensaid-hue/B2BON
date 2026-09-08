from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RotuloTipoTenant(Base):
    """Rótulo de exibição configurável por tipo interno de tenant na
    hierarquia (raio-X: os valores internos "distribuidor"/"revendedor"/
    "cliente" ficam fixos em toda regra de negócio —
    `tenant_service.TIPOS_TENANT_VALIDOS`/`_validar_hierarquia` — só o
    texto mostrado na tela muda aqui, editável por super_admin em
    Admin → Tenants. Ex.: hoje "distribuidor" aparece como "Master" e
    "revendedor" como "Vendedor", mas outro cliente da B2B ON pode preferir
    os nomes literais "Distribuidor"/"Revendedor" sem precisar de deploy."""

    __tablename__ = "rotulo_tipo_tenant"

    tipo: Mapped[str] = mapped_column(String, primary_key=True)
    rotulo: Mapped[str] = mapped_column(String)
