from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnriquecimentoFonte(Base):
    """Fonte de decisores sob o gerenciador de recursos (`app/contexts/enriquecimento/gerenciador.py`): configuração de PLATAFORMA, sem dado de cliente.

    `limite_mensal` é a franquia TÉCNICA do fornecedor (ex.: os créditos gratuitos do Hunter), contada em `consumido_periodo` e zerada a cada mês
    (`periodo`). Ela é independente da franquia comercial do cliente: ter saldo gratuito num fornecedor nunca aumenta o que o cliente contratou.
    `permite_uso_comercial` nasce nulo (não confirmado) e só o administrador altera, depois de conferir os termos do fornecedor. Nada aqui é mostrado
    ao cliente."""

    __tablename__ = "enriquecimento_fonte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String, unique=True)  # banco | site_institucional | hunter | ...
    camada: Mapped[str] = mapped_column(String)  # existente | gratuita | freemium | premium
    ativo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    prioridade: Mapped[int] = mapped_column(Integer, default=100)  # menor = consultada antes
    limite_mensal: Mapped[int | None] = mapped_column(Integer, nullable=True)  # nulo = sem teto técnico
    periodo: Mapped[str | None] = mapped_column(String, nullable=True)  # "AAAA-MM" a que `consumido_periodo` se refere
    consumido_periodo: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    permite_uso_comercial: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    politica_uso: Mapped[str | None] = mapped_column(String, nullable=True)
    # Disjuntor simples: falhas seguidas suspendem a fonte por um tempo; uma consulta bem-sucedida zera o contador.
    falhas_seguidas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    suspensa_ate: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultima_consulta_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class EnriquecimentoConsulta(Base):
    """Uma consulta de uma fonte para uma empresa de um tenant. Serve a três coisas: não repetir consulta que já deu resultado válido (cache por
    empresa e fonte, com validade configurável), contar a cota técnica e alimentar os indicadores administrativos (taxa de uso de recursos gratuitos,
    sucesso por fonte). Não guarda dado pessoal: o que a fonte devolveu virou `Decisor`; aqui só ficam as contagens."""

    __tablename__ = "enriquecimento_consulta"
    __table_args__ = (Index("ix_enriq_consulta_tenant_conta_fonte", "tenant_id", "conta_id", "fonte", "criado_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # empresa da pesquisa que originou a consulta (liga ao custo evitado)
    fonte: Mapped[str] = mapped_column(String, index=True)
    camada: Mapped[str] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String)  # ok | sem_resultados | erro | ignorada
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)  # sem dado pessoal: "cache", "cota_esgotada", "suspensa", código de erro da fonte
    encontrados: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # contatos devolvidos pela fonte
    novos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # decisores novos que passaram a existir por causa desta consulta
    creditos_fonte: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # consumo técnico informado pelo fornecedor
    duracao_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
