from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RedefinicaoSenha(Base):
    """Token de "esqueci minha senha" — mesmo padrão de `ConviteCadastro`
    (status disponivel|usado|expirado, sem DELETE pra manter o histórico
    de auditoria). `token` usa `secrets.token_urlsafe(32)` (bem mais
    entropia que os `token_hex(8)` de convite — este token, sozinho,
    autoriza trocar a senha de alguém, então precisa ser impossível de
    adivinhar/força-bruta, diferente de um código de convite que só um
    humano específico recebe e digita)."""

    __tablename__ = "redefinicao_senha"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[str] = mapped_column(String, default="disponivel")  # disponivel | usado | expirado
    validade_em: Mapped[datetime] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
