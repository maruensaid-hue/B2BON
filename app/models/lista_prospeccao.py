from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListaProspeccao(Base):
    """Lote nomeado de prospecção (ex.: "Evento Febraban 2026", "Security
    Leaders 2026") — desacoplado de ICP: cada lista pode servir um projeto
    de venda diferente, com seu próprio filtro de cargo-alvo pro
    enriquecimento de contatos. `icp_id` é opcional, só serve pra dar
    contexto de aderência (score) se a lista for correlata a um ICP já
    existente; sem ele, as contas da lista viram leads sem ICP (mesmo
    tratamento de leads avulsos já suportado em `Conta.icp_id`)."""

    __tablename__ = "lista_prospeccao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    icp_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    # None = usa o default genérico de seniority (SENIORIDADE_ALVO); lista
    # preenchida restringe a busca do Lusha só a esses cargos, economizando
    # consulta em vez de filtrar depois de já ter revelado o contato.
    cargos_alvo: Mapped[list | None] = mapped_column(JSON, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
