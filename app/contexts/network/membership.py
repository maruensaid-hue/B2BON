"""Membership (Fase 7): quem age em nome da empresa na rede.

Um usuário pertence a uma empresa (o tenant dele). Não há tabela própria
enquanto 1 usuário = 1 empresa (D-025). O que muda a identidade pública da
empresa exige ADMIN; o dia a dia da rede é de qualquer MEMBRO.
"""

from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.services.errors import NaoAutorizado

ADMIN = "ADMIN"
MEMBRO = "MEMBRO"

ACOES_ADMIN = frozenset({"editar_perfil", "gerenciar_relacionamentos", "reivindicar", "visibilidade_diretorio"})
ACOES_MEMBRO = frozenset({"publicar", "comentar", "mensagens", "conexoes", "intents", "salas"})


def papel_na_rede(papel_usuario: str) -> str:
    return ADMIN if papel_usuario in ("admin", "super_admin") else MEMBRO


def pode(papel_usuario: str, acao: str) -> bool:
    if acao in ACOES_MEMBRO:
        return True
    return acao in ACOES_ADMIN and papel_na_rede(papel_usuario) == ADMIN


def exigir(usuario: Usuario, acao: str) -> None:
    if not pode(usuario.papel, acao):
        raise NaoAutorizado("Só administradores da empresa podem fazer isso na rede.")


def membros(db: Session, tenant_id: str) -> list[dict]:
    usuarios = db.query(Usuario).filter_by(tenant_id=tenant_id, ativo=True).order_by(Usuario.nome).all()
    return [{"usuario_id": u.id, "nome": u.nome, "papel_na_rede": papel_na_rede(u.papel)} for u in usuarios]
