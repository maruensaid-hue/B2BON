from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CacheMercadoExterno(Base):
    """Cache persistido da Central de Negócios (raio-X 2026-09-24) —
    complementa o cache em memória de `central_negocios_service.py`
    (que se perde a cada cold start do plano free do Render). Sem isso,
    se a AwesomeAPI devolver 429 bem na primeira chamada depois de um
    restart, o fallback "stale" não tem nada em memória pra usar e o
    câmbio fica "indisponível" até uma chamada ter sorte. Só `chave`
    "mercado" é usada por ora — não estendido pra `noticias`, que não
    apresentou o mesmo bug."""

    __tablename__ = "cache_mercado_externo"

    chave: Mapped[str] = mapped_column(String, primary_key=True)
    valor: Mapped[dict] = mapped_column(JSON)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
