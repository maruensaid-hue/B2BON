from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
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
    origem: Mapped[str] = mapped_column(String)  # manual | predator_reuniao
    ganho_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    perdido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_perda: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
