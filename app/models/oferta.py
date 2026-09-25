from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Oferta(Base):
    __tablename__ = "oferta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    icp_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(String)
    diferenciais: Mapped[list] = mapped_column(JSON, default=list)
    provas_sociais: Mapped[list] = mapped_column(JSON, default=list)
    faixa_preco_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    faixa_preco_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "Ativa" = a oferta que entra no prompt de cadência (uma por tenant,
    # ver oferta_service.criar). Não significa "fora do portfólio".
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Offer Intelligence (master prompt §25, Fase 6). Tudo opcional: oferta
    # antiga continua válida; o que faltar vira lacuna declarada nas
    # recomendações, nunca valor inventado.
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    problemas_resolvidos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dores: Mapped[list | None] = mapped_column(JSON, nullable=True)
    casos_uso: Mapped[list | None] = mapped_column(JSON, nullable=True)
    personas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    industrias: Mapped[list | None] = mapped_column(JSON, nullable=True)
    requisitos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prerequisitos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    incompatibilidades: Mapped[list | None] = mapped_column(JSON, nullable=True)
    objecoes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    cases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Nomes de outras ofertas do tenant (texto livre, casado por nome).
    cross_sell: Mapped[list | None] = mapped_column(JSON, nullable=True)
    upsell: Mapped[list | None] = mapped_column(JSON, nullable=True)
    bundles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    perguntas_descoberta: Mapped[list | None] = mapped_column(JSON, nullable=True)
    criterios_qualificacao: Mapped[list | None] = mapped_column(JSON, nullable=True)
    modelo_precificacao: Mapped[str | None] = mapped_column(String, nullable=True)
    ticket_medio: Mapped[float | None] = mapped_column(Float, nullable=True)
    margem_media: Mapped[float | None] = mapped_column(Float, nullable=True)
    playbook: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Portfólio: entra no Next Best Offer / White Space. Independe de `ativo`.
    disponivel_para_venda: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
