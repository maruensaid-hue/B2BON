from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerfilEmpresa(Base):
    """Cartão de visita do assinante na Rede Social B2B (Onda C) — a
    partir do master prompt (Fase 1, §38 Corporate Profile), ganhou os
    campos de identidade/richness que faltavam (raio-X 2026-09-17).
    `status_verificacao` nasce aqui mas só é usado de fato a partir do
    fluxo de verificação (`VerificacaoEmpresa`), pra não precisar de
    duas migrações na mesma tabela."""

    __tablename__ = "perfil_empresa"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    nome_exibicao: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    setor: Mapped[str | None] = mapped_column(String, nullable=True)
    site: Mapped[str | None] = mapped_column(String, nullable=True)
    # URL colada pelo próprio usuário — sem upload/armazenamento de
    # arquivo novo, mesma simplicidade já usada em `site`.
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    capa_url: Mapped[str | None] = mapped_column(String, nullable=True)
    cnae_principal: Mapped[str | None] = mapped_column(String, nullable=True)
    # Texto livre — mesma convenção já usada em `ICP.porte`/`Conta.porte`.
    porte: Mapped[str | None] = mapped_column(String, nullable=True)
    sede_cidade: Mapped[str | None] = mapped_column(String, nullable=True)
    sede_uf: Mapped[str | None] = mapped_column(String, nullable=True)
    mercados: Mapped[list] = mapped_column(JSON, default=list)
    # Resumo de alto nível em texto livre — distinto das `Oferta`s
    # detalhadas já existentes (essas continuam sendo a fonte real de
    # produto/preço; isto é só o que aparece no cartão da Rede Social).
    produtos_servicos: Mapped[list] = mapped_column(JSON, default=list)
    tecnologias: Mapped[list] = mapped_column(JSON, default=list)
    certificacoes: Mapped[list] = mapped_column(JSON, default=list)
    redes_sociais: Mapped[dict] = mapped_column(JSON, default=dict)
    status_verificacao: Mapped[str] = mapped_column(String, default="nao_verificada")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
