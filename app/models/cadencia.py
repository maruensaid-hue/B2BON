from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cadencia(Base):
    __tablename__ = "cadencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    # Nullable: a cadência é um blueprint multicanal aplicado a um lote de
    # contas (E3-H1), não presa a uma única conta — o vínculo real com cada
    # conta se dá via Mensagem -> Decisor -> Conta.
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    # Capturados no momento da CRIAÇÃO da cadência (raio-X: bug real de
    # produção — a geração usava "o ICP/Oferta que estiver ativo agora
    # pro tenant", sem nenhum vínculo com a campanha desta cadência
    # específica; múltiplos ICPs ativos ao mesmo tempo são suportados de
    # propósito, para comparação — `icp_service.performance` —, então
    # trocar a Oferta ativa para uma campanha diferente corrompia
    # silenciosamente a geração de QUALQUER cadência já criada antes,
    # misturando o ICP de uma campanha com a Oferta de outra). Nullable
    # só para não quebrar cadências criadas antes desta coluna existir —
    # essas continuam caindo no fallback "o que estiver ativo agora".
    icp_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    oferta_id: Mapped[int | None] = mapped_column(ForeignKey("oferta.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String)
    canais: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String
    )  # rascunho | aguardando_aprovacao | ativa
    tipo: Mapped[str] = mapped_column(String, default="prospeccao")  # prospeccao | nutricao
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
