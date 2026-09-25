"""Corporate Rooms & Buying Rooms (Fase 11): participantes, documentos,
tarefas, reuniões e stakeholders da sala.

`tenant_id` é a empresa que criou o registro. `escopo`:
- `compartilhado`: as duas empresas da sala veem;
- `interno`: só a empresa que criou (ex.: o mapa de stakeholders que o
  vendedor faz do comitê do comprador nunca aparece para o comprador).
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class _DaSala:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sala_id: Mapped[int] = mapped_column(ForeignKey("sala_corporativa.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ParticipanteSala(_DaSala, Base):
    """Permissões por usuário. Sem participantes do lado de uma empresa, todos
    os usuários dela acessam (comportamento anterior); com participantes,
    só eles e os admins daquela empresa."""

    __tablename__ = "participante_sala"
    __table_args__ = (UniqueConstraint("sala_id", "usuario_id", name="uq_participante_sala"),)

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    papel: Mapped[str] = mapped_column(String)  # EDITOR | LEITOR


class DocumentoSala(_DaSala, Base):
    __tablename__ = "documento_sala"

    canal_id: Mapped[int | None] = mapped_column(ForeignKey("canal_sala.id"), nullable=True)
    escopo: Mapped[str] = mapped_column(String)
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)


class TarefaSala(_DaSala, Base):
    __tablename__ = "tarefa_sala"

    escopo: Mapped[str] = mapped_column(String)
    titulo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsavel_tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String)  # ABERTA | CONCLUIDA | CANCELADA
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)


class ReuniaoSala(_DaSala, Base):
    __tablename__ = "reuniao_sala"

    escopo: Mapped[str] = mapped_column(String)
    titulo: Mapped[str] = mapped_column(String)
    inicio: Mapped[datetime] = mapped_column(DateTime)
    fim: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    link: Mapped[str | None] = mapped_column(String, nullable=True)
    pauta: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)


class StakeholderSala(_DaSala, Base):
    """Buying Room: comitê de compra. `lado` = de qual empresa é a pessoa
    (VENDEDOR | COMPRADOR); `papel` = BuyingRole do modelo canônico."""

    __tablename__ = "stakeholder_sala"

    escopo: Mapped[str] = mapped_column(String)
    lado: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String)
    cargo: Mapped[str | None] = mapped_column(String, nullable=True)
    papel: Mapped[str] = mapped_column(String)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
