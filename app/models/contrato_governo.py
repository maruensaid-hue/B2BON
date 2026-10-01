"""B2B ON Government (D-072): contrato, períodos anuais, componentes, recebimentos,
política de comissão, pipeline e templates comerciais.

Separação contábil: cada valor contratado é um **componente** com tipo próprio
(licença, implantação, subscrição inicial, renovação, serviços, créditos). Bookings,
ARR, TCV e Cash-In são derivados dos componentes e dos recebimentos; nenhum valor
total é guardado como receita recorrente. Os valores do contrato são uma cópia do
catálogo no momento da contratação: mudar o preço público não muda contrato antigo.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PoliticaComissao(Base):
    """Regras de comissão por tipo de componente, versionadas (mudar a política
    cria uma versão nova; o contrato guarda a cópia da versão em que nasceu)."""

    __tablename__ = "politica_comissao"
    __table_args__ = (UniqueConstraint("codigo", "versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String)  # GOVERNMENT
    versao: Mapped[int] = mapped_column(Integer)
    regras: Mapped[dict] = mapped_column(JSON)  # {"gatilho": ..., "componentes": {TIPO: {"comissionavel": bool, "taxa": float}}}
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TemplateDocumentoComercial(Base):
    """Template configurável de proposta/contrato (texto com marcadores `{licenca}` etc.).
    Não é texto jurídico: é o resumo comercial dos componentes."""

    __tablename__ = "template_documento_comercial"
    __table_args__ = (UniqueConstraint("codigo", "versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String)  # PROPOSTA_GOVERNO
    versao: Mapped[int] = mapped_column(Integer)
    corpo: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OportunidadeGoverno(Base):
    """Pipeline Government da B2B ON (operação da plataforma, super_admin), separado
    da quota privada de New MRR."""

    __tablename__ = "oportunidade_governo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String)
    entidade_governamental: Mapped[str] = mapped_column(String)
    estagio: Mapped[str] = mapped_column(String, default="OPPORTUNITY_IDENTIFIED")
    referencia_processo: Mapped[str | None] = mapped_column(String, nullable=True)
    origem: Mapped[str | None] = mapped_column(String, nullable=True)
    data_prevista_fechamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_estimado_licenca: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    valor_estimado_assinatura: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    valor_estimado_servicos: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    probabilidade: Mapped[float] = mapped_column(Float, default=0)
    plano_id: Mapped[int | None] = mapped_column(ForeignKey("plano.id"), nullable=True, index=True)
    representante_id: Mapped[int | None] = mapped_column(ForeignKey("representante.id"), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenant.id"), nullable=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContratoGoverno(Base):
    __tablename__ = "contrato_governo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano.id"), index=True)
    oportunidade_id: Mapped[int | None] = mapped_column(ForeignKey("oportunidade_governo.id"), nullable=True, index=True)
    modelo_cobranca: Mapped[str] = mapped_column(String)  # GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION | GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY
    referencia_contrato: Mapped[str] = mapped_column(String)
    entidade_governamental: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ATIVO")  # ATIVO | ENCERRADO | CANCELADO
    assinado_em: Mapped[date] = mapped_column(Date)
    # Cópia do catálogo na contratação (não muda se o preço público mudar)
    valor_licenca: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    valor_implantacao: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    valor_assinatura_anual: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    creditos_ia_anuais: Mapped[int] = mapped_column(Integer)
    regra_reajuste: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # descrição contratual; sem índice fixo no código
    politica_comissao: Mapped[dict] = mapped_column(JSON)  # cópia da versão vigente na contratação
    politica_comissao_versao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    representante_id: Mapped[int | None] = mapped_column(ForeignKey("representante.id"), nullable=True, index=True)
    divisao_comissao: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{"representante_id": int, "fracao": float}]
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PeriodoAssinaturaGoverno(Base):
    """Um período anual da subscrição. `numero` 1 = contratação inicial; 2+ = renovações."""

    __tablename__ = "periodo_assinatura_governo"
    __table_args__ = (UniqueConstraint("contrato_id", "numero"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contrato_id: Mapped[int] = mapped_column(ForeignKey("contrato_governo.id"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    inicio: Mapped[date] = mapped_column(Date)
    fim: Mapped[date] = mapped_column(Date)  # data de renovação
    valor_assinatura: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    valor_reajuste: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String, default="ATIVO")  # ATIVO | ENCERRADO | CANCELADO
    status_renovacao: Mapped[str] = mapped_column(String, default="NAO_INICIADA")  # NAO_INICIADA | NOTIFICADA | RENOVADA | NAO_RENOVADA
    notificacao_renovacao_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lote_creditos_id: Mapped[int | None] = mapped_column(ForeignKey("lote_credito.id"), nullable=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ComponenteContratoGoverno(Base):
    __tablename__ = "componente_contrato_governo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contrato_id: Mapped[int] = mapped_column(ForeignKey("contrato_governo.id"), index=True)
    periodo_id: Mapped[int | None] = mapped_column(ForeignKey("periodo_assinatura_governo.id"), nullable=True, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    recorrente: Mapped[bool] = mapped_column(Boolean, default=False)  # entra no ARR
    comissionavel: Mapped[bool] = mapped_column(Boolean, default=False)
    taxa_comissao: Mapped[float | None] = mapped_column(Float, nullable=True)
    # D-076: classificação fiscal do componente (SOFTWARE_LICENSE, SAAS_SUBSCRIPTION, IMPLEMENTATION, CONSULTING,
    # SUPPORT). Vazio = padrão do tipo; serviço adicional sem classificação aguarda o Tax Profile.
    tipo_receita: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_em: Mapped[date] = mapped_column(Date)
    cancelado: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecebimentoGoverno(Base):
    """Cash-In: pagamento efetivamente recebido, por componente (parcelas permitidas)."""

    __tablename__ = "recebimento_governo"
    __table_args__ = (UniqueConstraint("contrato_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contrato_id: Mapped[int] = mapped_column(ForeignKey("contrato_governo.id"), index=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("componente_contrato_governo.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    recebido_em: Mapped[date] = mapped_column(Date)
    referencia: Mapped[str | None] = mapped_column(String, nullable=True)  # NF, empenho, ordem bancária
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    estornado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_estorno: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
