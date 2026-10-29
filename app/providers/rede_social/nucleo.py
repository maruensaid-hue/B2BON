from sqlalchemy.orm import Session

from app.db import rls
from app.models.usuario import Usuario
from app.providers.rede_social.base import RedeSocialProvider


class NucleoRedeSocialProvider(RedeSocialProvider):
    """Implementação real da porta de Rede Social B2B (Onda C) — um
    identificador é "intra-rede" quando já pertence a um `Usuario`
    cadastrado em qualquer tenant, ou seja, a pessoa indicada já é
    contato de um assinante da B2B ON."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def eh_assinante(self, identificador: str) -> bool:
        # Procurar um e-mail em QUALQUER tenant é a busca por e-mail (política `login` do banco: só a linha cujo e-mail coincide), não uma leitura livre de `usuario`.
        with rls.contexto_busca(self._db, rls.ESCOPO_LOGIN, identificador.strip().lower()):
            return self._db.query(Usuario).filter_by(email=identificador).first() is not None
