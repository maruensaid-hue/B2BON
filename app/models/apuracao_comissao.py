"""Parâmetros financeiros e memória de cálculo das comissões (D-074).

- `PerfilTributario` (Tax Profile): carga tributária por regime, vigência, tipo de receita e município, com componentes
  (ex.: IRPJ, CSLL, PIS, COFINS, ISS) — nenhuma alíquota no código.
- `ModeloCustoInfra` (Infrastructure Cost Model): alocação do custo de infraestrutura atribuível à receita (fixa,
  percentual, por uso de IA, por tenant, por produto ou híbrida), com vigência.
- `ApuracaoComissao`: uma por recebimento (pagamento de plano privado ou recebimento Government). Guarda o snapshot do
  cálculo — receita bruta, perfil e valor de impostos, modelo e valor de infraestrutura, Margem Comissionável Líquida —
  para que mudança futura de parâmetro não altere a memória de uma comissão já calculada ou paga.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerfilTributario(Base):
    __tablename__ = "perfil_tributario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regime: Mapped[str] = mapped_column(String)  # ex.: LUCRO_PRESUMIDO
    vigente_de: Mapped[date] = mapped_column(Date)
    vigente_ate: Mapped[date | None] = mapped_column(Date, nullable=True)  # exclusivo
    tipo_receita: Mapped[str] = mapped_column(String, default="*")  # SAAS | LICENCA_SOFTWARE | SERVICO | * (qualquer)
    municipio: Mapped[str | None] = mapped_column(String, nullable=True)
    componentes: Mapped[list] = mapped_column(JSON)  # [{"nome": "PIS", "aliquota": 0.0065}, ...]
    aliquota_efetiva: Mapped[float] = mapped_column(Float)
    metodo_calculo: Mapped[str] = mapped_column(String, default="SOBRE_RECEITA_RECEBIDA")
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ModeloCustoInfra(Base):
    __tablename__ = "modelo_custo_infra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String)
    vigente_de: Mapped[date] = mapped_column(Date)
    vigente_ate: Mapped[date | None] = mapped_column(Date, nullable=True)  # exclusivo
    metodo: Mapped[str] = mapped_column(String)  # FIXED | PERCENTAGE | USAGE | TENANT | PRODUCT | HYBRID
    componentes: Mapped[list] = mapped_column(JSON)
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApuracaoComissao(Base):
    __tablename__ = "apuracao_comissao"
    __table_args__ = (UniqueConstraint("pagamento_licenca_id"), UniqueConstraint("recebimento_governo_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    origem: Mapped[str] = mapped_column(String)  # PAGAMENTO_LICENCA | RECEBIMENTO_GOVERNO
    pagamento_licenca_id: Mapped[int | None] = mapped_column(ForeignKey("pagamento_licenca.id"), nullable=True)
    recebimento_governo_id: Mapped[int | None] = mapped_column(ForeignKey("recebimento_governo.id"), nullable=True)
    segmento: Mapped[str] = mapped_column(String)  # PRIVATE | GOVERNMENT
    produto: Mapped[str] = mapped_column(String)  # nome do plano
    tipo_receita: Mapped[str] = mapped_column(String)
    componente_tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    recebido_em: Mapped[date] = mapped_column(Date)
    receita_bruta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    perfil_tributario_id: Mapped[int | None] = mapped_column(ForeignKey("perfil_tributario.id"), nullable=True, index=True)
    aliquota_tributaria: Mapped[float | None] = mapped_column(Float, nullable=True)
    impostos: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    modelo_custo_infra_id: Mapped[int | None] = mapped_column(ForeignKey("modelo_custo_infra.id"), nullable=True, index=True)
    custo_infra: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # inclui o custo de IA, quando o modelo o aloca
    custo_ia: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    custo_ia_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # até onde o custo de IA do tenant já foi atribuído
    margem_comissionavel_liquida: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String)  # AWAITING_COST_PARAMETERS | CALCULATED | REVERSED
    parametros_faltantes: Mapped[list | None] = mapped_column(JSON, nullable=True)  # TAX_PROFILE | INFRASTRUCTURE_COST
    detalhe: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calculado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
