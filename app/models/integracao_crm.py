"""Escrita no CRM do cliente (D-087): vínculos, fila de saída, índice de
deduplicação e autorizações OAuth em andamento.

- `VinculoExterno`: registro interno ↔ id no CRM, por conexão. É o que torna
  a escrita idempotente (reenvio atualiza/reaproveita, nunca duplica).
- `EnvioCrm`: fila de saída por conexão (mesmo padrão do outbox de webhooks):
  retry com backoff, desistência após N tentativas, reprocesso manual.
- `RegistroCrmExterno`: o que o CRM do cliente já sabe (cliente, negócio
  aberto, opt-out) indexado por hash de CNPJ/domínio/e-mail — o PREDATOR
  consulta antes de abordar. Só hash: nenhum dado pessoal cru do CRM aqui.
- `AutorizacaoOauthPendente`: tokens recebidos no callback OAuth aguardando
  o usuário que iniciou concluir com o próprio login (anti-CSRF).
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class VinculoExterno(Base):
    __tablename__ = "vinculo_externo"
    __table_args__ = (UniqueConstraint("conexao_id", "entidade", "id_interno", name="uq_vinculo_externo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conexao_id: Mapped[int] = mapped_column(ForeignKey("conexao_integracao.id"), index=True)
    entidade: Mapped[str] = mapped_column(String)  # empresa | pessoa | negocio | atividade | tarefa
    id_interno: Mapped[str] = mapped_column(String)
    id_externo: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EnvioCrm(Base):
    __tablename__ = "envio_crm"
    __table_args__ = (UniqueConstraint("conexao_id", "chave", name="uq_envio_crm_chave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conexao_id: Mapped[int] = mapped_column(ForeignKey("conexao_integracao.id"), index=True)
    operacao: Mapped[str] = mapped_column(String)
    id_interno: Mapped[str] = mapped_column(String)
    chave: Mapped[str] = mapped_column(String)  # idempotência: mesma chave = mesmo envio
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    status: Mapped[str] = mapped_column(String, default="pendente", index=True)  # pendente | enviado | pulado | desistido
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    proxima_tentativa_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    ultimo_erro: Mapped[str | None] = mapped_column(String, nullable=True)
    resultado: Mapped[str | None] = mapped_column(String, nullable=True)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RegistroCrmExterno(Base):
    __tablename__ = "registro_crm_externo"
    __table_args__ = (UniqueConstraint("conexao_id", "tipo_chave", "chave_hash", name="uq_registro_crm_externo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conexao_id: Mapped[int] = mapped_column(ForeignKey("conexao_integracao.id"), index=True)
    tipo_chave: Mapped[str] = mapped_column(String)  # cnpj | dominio | email
    chave_hash: Mapped[str] = mapped_column(String, index=True)
    cliente: Mapped[bool] = mapped_column(Boolean, default=False)
    negocio_aberto: Mapped[bool] = mapped_column(Boolean, default=False)
    optout: Mapped[bool] = mapped_column(Boolean, default=False)
    id_externo: Mapped[str | None] = mapped_column(String, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AutorizacaoOauthPendente(Base):
    __tablename__ = "autorizacao_oauth_pendente"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # referência aleatória (token_urlsafe)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    sistema: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String)
    credenciais: Mapped[str] = mapped_column(TextoCriptografado)
    expira_em: Mapped[datetime] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
