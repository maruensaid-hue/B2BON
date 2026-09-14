from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Negocio(Base):
    """Oportunidade de venda — o "kanban de clientes" do CRM Core (Onda B).

    `origem="predator_reuniao"` nasce sozinho quando `reuniao_service.confirmar`
    chama `CrmProvider.criar_ou_atualizar_oportunidade` (E6-H2, PREDATOR);
    `origem="manual"` é cadastro direto do vendedor.
    """

    __tablename__ = "negocio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    vendedor_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    # Contato que conduz a oportunidade do lado do cliente — nulo pra não
    # quebrar negócios antigos/os que o PREDATOR já cria sozinho, mas
    # exigido pela camada de serviço no cadastro manual (crm_service).
    decisor_id: Mapped[int | None] = mapped_column(ForeignKey("decisor.id"), nullable=True)
    estagio_id: Mapped[int] = mapped_column(ForeignKey("estagio_funil.id"))
    nome: Mapped[str] = mapped_column(String)
    valor: Mapped[float] = mapped_column(Float, default=0.0)
    probabilidade: Mapped[int] = mapped_column(Integer, default=50)
    origem: Mapped[str] = mapped_column(String)  # manual | predator_reuniao | crm_import
    ganho_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    perdido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_perda: Mapped[str | None] = mapped_column(String, nullable=True)
    # Identifica a linha de origem de uma importação de CSV (ID do negócio
    # na plataforma de onde veio, ou "b2bon-{id}" quando o CSV é um export
    # nosso) — sem isso, reimportar o mesmo arquivo duplicaria negócios em
    # vez de atualizar (raio-X 2026-09-14). Nulo pra negócios criados
    # manualmente, pelo PREDATOR, ou importados sem uma coluna de ID
    # externo mapeada (reimportar esses, nesse caso, duplica).
    chave_importacao: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# Único-quando-presente (raio-X 2026-09-14, import/export de CSV): permite
# reimportar o mesmo arquivo sem duplicar negócios — a segunda importação
# com a mesma chave atualiza em vez de criar (garantido no banco, não por
# checagem prévia em código — mesmo padrão de `RegistroOportunidade`).
Index(
    "ix_negocio_chave_importacao_unica",
    Negocio.tenant_id,
    Negocio.chave_importacao,
    unique=True,
    postgresql_where=(Negocio.chave_importacao.isnot(None)),
    sqlite_where=(Negocio.chave_importacao.isnot(None)),
)
