from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
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

    # Hierarquia Distribuidor -> Revendedor -> Cliente (raio-X: "distribuidor"
    # solicitou API de provisionamento/billing; fundação é modelar a árvore
    # antes de expor qualquer API). Default "cliente" preserva o
    # comportamento de todo tenant já existente, que não tem hierarquia.
    tipo: Mapped[str] = mapped_column(String, default="cliente", server_default="cliente")

    # Auto-referência dentro da própria tabela `tenant` — diferente da
    # convenção documentada acima (nenhuma FK formal DE OUTRAS tabelas
    # para esta), aqui é a própria tabela se referenciando, caso contido.
    tenant_pai_id: Mapped[str | None] = mapped_column(String, ForeignKey("tenant.id"), nullable=True)

    # "direta": tenant paga a própria licença (fluxo atual do Mercado
    # Pago, inalterado). "consolidada": status de pagamento é herdado do
    # tenant_pai_id (quem fatura por fora é o Distribuidor/Revendedor) —
    # ver `exigir_licenca_ativa` em app/api/deps.py.
    modo_cobranca: Mapped[str] = mapped_column(String, default="direta", server_default="direta")
