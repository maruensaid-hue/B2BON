from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RelacionamentoEmpresarial(Base):
    """Business Graph foundation (master prompt §40-42, Fase 1D, raio-X
    2026-09-17) — o master prompt é explícito (§42): "não introduza
    graph database prematuramente... PostgreSQL + edge tables" antes de
    qualquer coisa nova. Edge tipada empresa-a-empresa, distinta em
    propósito de `ConexaoEmpresa` (conexão social bilateral com aceite):
    um relacionamento comercial pode existir mesmo sem conexão aceita
    (é uma afirmação, não um convite), e é o que a Fase 3 (Opportunity
    Signal) vai consumir depois."""

    __tablename__ = "relacionamento_empresarial"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_origem: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    # Nulo quando o destino é uma empresa ainda não reivindicada (Fase 7):
    # a aresta aponta só para `empresa_destino_id`.
    tenant_id_destino: Mapped[str | None] = mapped_column(ForeignKey("tenant.id"), index=True, nullable=True)
    # Company Identity das duas pontas (Fase 7, §28).
    empresa_origem_id: Mapped[int | None] = mapped_column(ForeignKey("empresa_rede.id"), nullable=True)
    empresa_destino_id: Mapped[int | None] = mapped_column(ForeignKey("empresa_rede.id"), nullable=True, index=True)
    # SUPPLIER_OF | CUSTOMER_OF | PARTNER_OF | RESELLER_OF | DISTRIBUTOR_OF |
    # INTEGRATES_WITH | USES_TECHNOLOGY | PROVIDES_SERVICE | PROVIDES_PRODUCT |
    # INVESTS_IN | INTERESTED_IN | LOOKING_FOR (master prompt §40)
    tipo: Mapped[str] = mapped_column(String)
    visibilidade: Mapped[str] = mapped_column(String, default="publica")  # publica | conexoes | privada
    confianca: Mapped[str] = mapped_column(String, default="autodeclarada")  # autodeclarada | confirmada_pela_contraparte
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    # §28: source e validity. DECLARADA (autodeclarada) | CONFIRMADA (pela
    # contraparte). `confianca` acima é o estado de verificação.
    fonte: Mapped[str] = mapped_column(String, default="DECLARADA", server_default="DECLARADA")
    valido_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    valido_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    metadados: Mapped[dict] = mapped_column(JSON, default=dict)
