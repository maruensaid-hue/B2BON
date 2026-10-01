"""Parâmetros financeiros e memória de cálculo das comissões (D-074).

- `PerfilTributario` (Tax Profile): tributos por regime, vigência, tipo de receita, município e código de serviço, um
  componente por tributo (IRPJ, adicional de IRPJ, CSLL, PIS, COFINS, ISS, CBS, IBS, outros) — nenhuma alíquota no código.
- Custo de infraestrutura: Infrastructure Cost Pool (`custo_infraestrutura.py`, D-076).
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
    item_lista_servico: Mapped[str | None] = mapped_column(String, nullable=True)  # LC 116, ex.: 1.05
    codigo_servico: Mapped[str | None] = mapped_column(String, nullable=True)  # código de serviço municipal, ex.: 2800
    versao_legal: Mapped[str | None] = mapped_column(String, nullable=True)  # base legal da versão (ex.: LC 224/2025)
    # D-075: um componente por tributo — {"tributo": "IRPJ", "aliquota": 0.15, "base": "PRESUNCAO", "presuncao": 0.32}.
    # O imposto é calculado pelo Tax Engine componente a componente; nenhuma alíquota efetiva única vira regra.
    componentes: Mapped[list] = mapped_column(JSON)
    aliquota_efetiva: Mapped[float | None] = mapped_column(Float, nullable=True)  # legado D-074 (não usado no cálculo)
    metodo_calculo: Mapped[str] = mapped_column(String, default="SOBRE_RECEITA_RECEBIDA")
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
    # D-076: custo provisionado (conservador, usado na comissão) e custo real ficam separados
    custo_infra: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # provisionado (comissão)
    custo_infra_real: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    meses_infra: Mapped[float | None] = mapped_column(Float, nullable=True)  # meses de operação que o recebimento remunera
    custo_direto_ate: Mapped[str | None] = mapped_column(String(7), nullable=True)  # competência até onde o custo direto foi atribuído
    custo_ia: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    custo_ia_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # até onde o custo de IA do tenant já foi atribuído
    margem_comissionavel_liquida: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String)  # AWAITING_COST_PARAMETERS | CALCULATED | REVERSED
    parametros_faltantes: Mapped[list | None] = mapped_column(JSON, nullable=True)  # TAX_PROFILE | INFRASTRUCTURE_COST
    detalhe: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calculado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PeriodoStatusTributario(Base):
    """TaxStatusPeriod (D-078): situação efetiva de um grupo de tributos numa vigência — hoje CBS/IBS de 2026
    (WAIVED_BY_COMPLIANCE, COMPENSATED, PAYABLE, PENDING_COMPLIANCE_CONFIRMATION). Mudança de situação = período novo; o
    histórico (e as comissões calculadas com ele) não muda."""

    __tablename__ = "periodo_status_tributario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grupo: Mapped[str] = mapped_column(String)  # CBS_IBS
    status: Mapped[str] = mapped_column(String)
    vigente_de: Mapped[date] = mapped_column(Date)
    vigente_ate: Mapped[date | None] = mapped_column(Date, nullable=True)  # inclusivo
    motivo: Mapped[str] = mapped_column(String)
    aprovado_por: Mapped[str] = mapped_column(String)
    referencia_evidencia: Mapped[str | None] = mapped_column(String, nullable=True)
    referencia_legal: Mapped[str | None] = mapped_column(String, nullable=True)
    alterado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
