"""Infrastructure Cost Pool (D-076): fornecedores/planos da infraestrutura da CyberFort, com custo real e custo
provisionado separados, capacidade contratada, uso medido, custos diretamente atribuíveis a um tenant e alertas de
capacidade. Nenhum fornecedor ou valor fica no código: tudo é cadastrado no Admin → Parâmetros financeiros.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComponenteInfra(Base):
    """Um fornecedor/serviço/plano do pool. Custos no ciclo de cobrança e na moeda informados."""

    __tablename__ = "componente_infra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fornecedor: Mapped[str] = mapped_column(String)  # provider (ex.: Render, Neon, Lusha)
    servico: Mapped[str] = mapped_column(String)  # service
    categoria: Mapped[str] = mapped_column(String)  # HOSTING | DATABASE | STORAGE | ... (tipos.CATEGORIAS_INFRA)
    plano: Mapped[str | None] = mapped_column(String, nullable=True)  # plano contratado hoje
    plano_referencia: Mapped[str | None] = mapped_column(String, nullable=True)  # plano máximo/de referência
    ciclo_cobranca: Mapped[str] = mapped_column(String)  # MONTHLY | QUARTERLY | ANNUAL
    moeda: Mapped[str] = mapped_column(String(3))
    custo_contratado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # plano atual, por ciclo
    custo_referencia: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # plano de referência, por ciclo
    custo_real: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # efetivamente incorrido, por ciclo
    capacidade_contratada: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    uso_atual: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unidade_uso: Mapped[str | None] = mapped_column(String, nullable=True)
    politica_custo: Mapped[str] = mapped_column(String)  # MAX_CONTRACTED_PLAN | ACTUAL_COST
    metodo_alocacao: Mapped[str] = mapped_column(String)  # WEIGHTED | DIRECT
    # Pool de custo (D-077): INFRASTRUCTURE | DATA_PROVIDER | AI_COST — uma despesa pertence a um pool só
    contabilizacao: Mapped[str] = mapped_column(String)
    # D-077: modelo de preço, aplicabilidade à arquitetura real e fonte do preço
    modelo_preco: Mapped[str] = mapped_column(String, default="FIXED_PLAN", server_default="FIXED_PLAN")  # FIXED_PLAN | USAGE_BASED | CUSTOM
    status_arquitetura: Mapped[str] = mapped_column(String, default="APPLICABLE", server_default="APPLICABLE")
    provisionado_para_comissao: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    funcao_arquitetural: Mapped[str | None] = mapped_column(String, nullable=True)  # ex.: PRIMARY_DATABASE, WEB_COMPUTE
    coexistencia_justificada: Mapped[str | None] = mapped_column(String, nullable=True)  # dois componentes na mesma função
    url_fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo_fonte: Mapped[str] = mapped_column(String, default="MANUAL_APPROVED", server_default="MANUAL_APPROVED")
    verificado_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    proxima_revisao_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    override_manual: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    motivo_override: Mapped[str | None] = mapped_column(String, nullable=True)
    atributos: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # preços unitários, créditos/assentos incluídos
    vigente_de: Mapped[date] = mapped_column(Date)
    vigente_ate: Mapped[date | None] = mapped_column(Date, nullable=True)  # exclusivo
    observacoes: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UsoCapacidadeInfra(Base):
    """Histórico do uso medido de um componente (base do monitoramento e da projeção de esgotamento)."""

    __tablename__ = "uso_capacidade_infra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("componente_infra.id"), index=True)
    medido_em: Mapped[datetime] = mapped_column(DateTime)
    uso: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    registrado_por: Mapped[str | None] = mapped_column(String, nullable=True)


class CustoDiretoInfra(Base):
    """Custo diretamente mensurável de um tenant num mês (Direct Attribution), na moeda do componente."""

    __tablename__ = "custo_direto_infra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("componente_infra.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    competencia: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    custo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AlertaCapacidadeInfra(Base):
    """Recomendação/alerta de capacidade (80/90/100% por padrão). Nada é contratado sozinho: a decisão é humana."""

    __tablename__ = "alerta_capacidade_infra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("componente_infra.id"), index=True)
    nivel: Mapped[str] = mapped_column(String)  # REVIEW | CRITICAL | CAPACITY_REACHED
    utilizacao: Mapped[float] = mapped_column(Float)
    mensagem: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ABERTO")  # ABERTO | DECIDIDO
    decisao: Mapped[str | None] = mapped_column(String, nullable=True)
    decidido_por: Mapped[str | None] = mapped_column(String, nullable=True)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EnvelopeCapacidade(Base):
    """Capacity Envelope (D-077) de um componente com preço por uso (ex.: Neon): quanto a CyberFort decide provisionar.
    Custo = horas de computação × preço por unidade + armazenamento × preço por GB + outros custos aplicáveis.
    `benchmark_only` = cenário publicado pelo fornecedor, guardado como referência e nunca usado como custo."""

    __tablename__ = "envelope_capacidade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("componente_infra.id"), index=True)
    max_unidades_computo: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    horas_computo_provisionadas: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    armazenamento_gb_provisionado: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    preco_unidade_computo: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    preco_armazenamento_gb: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    outros_custos: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{"descricao": ..., "valor": ...}]
    custo_mensal_estimado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    moeda: Mapped[str] = mapped_column(String(3))
    vigente_de: Mapped[date] = mapped_column(Date)
    vigente_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    verificado_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    benchmark_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    observacoes: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
