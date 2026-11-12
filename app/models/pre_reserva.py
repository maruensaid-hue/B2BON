from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoPreReserva(Base):
    """Formulário público de pré-reserva de data (palestra, workshop, visita técnica…) de um tenant.

    Usa o mesmo código do `LinkCapturaLead` do tenant: a página pública `/pre-reserva/{codigo}` só aparece quando esta configuração existe e está ativa. As datas
    oferecidas são as de `datas_disponiveis` que ainda não têm pré-reserva ativa e respeitam a antecedência mínima — o que o cliente vê é a agenda real.
    """

    __tablename__ = "configuracao_pre_reserva"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), primary_key=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    marca: Mapped[str] = mapped_column(String)  # nome exibido na página (pode ser uma marca diferente da razão social do tenant)
    titulo: Mapped[str] = mapped_column(String)  # o que está sendo reservado, ex.: "Palestra O Vendedor Tubarão"
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    site: Mapped[str | None] = mapped_column(String, nullable=True)
    datas_disponiveis: Mapped[list] = mapped_column(JSON, default=list)  # ["2026-12-03", ...]
    antecedencia_minima_dias: Mapped[int] = mapped_column(Integer, default=10)
    horas_pre_reserva: Mapped[int] = mapped_column(Integer, default=48)
    valor_presencial: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_online: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentual_sinal: Mapped[int] = mapped_column(Integer, default=50)
    formas_pagamento: Mapped[list] = mapped_column(JSON, default=list)  # ["pix", "boleto", "cartao_credito", "cartao_debito"]
    condicao_especial: Mapped[str | None] = mapped_column(Text, nullable=True)  # texto livre, ex.: o bônus
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PreReserva(Base):
    """Uma data segurada por um cliente pelo formulário público. Nasce junto com a Conta, o Decisor e o Negócio no CRM do tenant.

    `status`: `pre_reservada` (dentro do prazo sem custo, `expira_em`), `confirmada` (sinal pago) ou `cancelada` (prazo vencido sem pagamento, desistência). Só
    `cancelada` devolve a data para a agenda — o índice único parcial abaixo impede duas pré-reservas ativas no mesmo dia, mesmo com dois envios simultâneos.
    """

    __tablename__ = "pre_reserva"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"), index=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocio.id"), index=True)
    data_evento: Mapped[date] = mapped_column(Date)
    formato: Mapped[str] = mapped_column(String)  # presencial | online
    cidade: Mapped[str | None] = mapped_column(String, nullable=True)
    participantes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forma_pagamento: Mapped[str | None] = mapped_column(String, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="pre_reservada")
    expira_em: Mapped[datetime] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


Index(
    "ix_pre_reserva_data_ativa_unica",
    PreReserva.tenant_id,
    PreReserva.data_evento,
    unique=True,
    postgresql_where=(PreReserva.status != "cancelada"),
    sqlite_where=(PreReserva.status != "cancelada"),
)
