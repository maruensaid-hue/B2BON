from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS = ("NAO_REIVINDICADA", "REIVINDICADA", "VERIFICADA", "MESCLADA")
ORIGENS = ("TENANT", "DECLARADA_POR_TERCEIRO", "OFICIAL")


class EmpresaRede(Base):
    """Company Identity da Business Network (master prompt §27, Fase 7).

    A empresa é o objeto econômico da rede. Com `tenant_id`, ela foi
    reivindicada por um cliente da B2B ON (REIVINDICADA; VERIFICADA depois
    da verificação aprovada). Sem `tenant_id`, é uma empresa citada por CNPJ
    por outra (NAO_REIVINDICADA): só CNPJ e nome, nunca dado privado. Quando
    o dono reivindica, ela é MESCLADA na identidade do tenant e as arestas
    passam a apontar para ele.
    """

    __tablename__ = "empresa_rede"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenant.id"), nullable=True, unique=True)
    cnpj: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    razao_social: Mapped[str | None] = mapped_column(String, nullable=True)
    nome_exibicao: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    origem: Mapped[str] = mapped_column(String)
    criado_por_tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mesclada_em_id: Mapped[int | None] = mapped_column(ForeignKey("empresa_rede.id"), nullable=True)
    reivindicada_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
