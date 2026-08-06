from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaterialOferta(Base):
    __tablename__ = "material_oferta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey("oferta.id"))
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    # Blob direto no banco (raio-X de produção) — o disco do Render é
    # efêmero (some a cada redeploy) e o nome de arquivo vindo do usuário
    # não é seguro para virar path (traversal); guardar o conteúdo aqui
    # elimina os dois problemas de uma vez.
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
