from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplateProposta(Base):
    """Modelo único de proposta comercial por tenant (singleton, get-or-create
    em `template_proposta_service.obter_ou_criar`) — parte "institucional"
    (texto, logo, termo de aceite) salva como padrão para todas as propostas
    geradas; as tabelas de produtos/serviços têm itens padrão próprios
    (`ItemTemplateProposta`), editáveis por proposta sem alterar o modelo."""

    __tablename__ = "template_proposta"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    texto_introdutorio: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_tipo_mime: Mapped[str | None] = mapped_column(String, nullable=True)
    termo_aceite: Mapped[str | None] = mapped_column(Text, nullable=True)
    mostrar_tabela_produtos: Mapped[bool] = mapped_column(Boolean, default=True)
    mostrar_tabela_servicos: Mapped[bool] = mapped_column(Boolean, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ItemTemplateProposta(Base):
    """Linha padrão de uma das duas tabelas de preço (produto ou serviço)
    do modelo de proposta do tenant."""

    __tablename__ = "item_template_proposta"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("template_proposta.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)  # produto | servico
    ordem: Mapped[int] = mapped_column(default=0)
    descricao: Mapped[str] = mapped_column(String)
    valor: Mapped[float | None] = mapped_column(nullable=True)
