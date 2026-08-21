from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecorteCnpjEstado(Base):
    """Estado (linha única, id fixo) do recorte de CNPJ carregado
    automaticamente via cron (`cnpj_recorte_service`) — sem isto, cada
    execução do cron baixaria de novo os shards da Receita Federal
    (centenas de MB a alguns GB) mesmo quando nenhum ICP novo surgiu desde
    a última carga."""

    __tablename__ = "recorte_cnpj_estado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mes_competencia: Mapped[str] = mapped_column(String)
    cnae_codigos_cobertos: Mapped[list] = mapped_column(JSON, default=list)
    ufs_cobertos: Mapped[list] = mapped_column(JSON, default=list)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
