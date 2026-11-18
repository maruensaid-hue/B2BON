"""Anotações da daily do gestor no MAP (pedido do PO em 18/11/2026).

Só gestor (admin/super_admin) escreve. Por padrão a nota volta no dia seguinte (data de Brasília); ele pode escolher outra data, nunca no passado. Na data
marcada ela aparece em destaque no topo do MAP e continua lá até ele marcar "vista" — assim uma nota para sábado não some antes da segunda-feira.
A nota é privada de quem escreveu (por tenant): outro gestor do mesmo tenant não a vê, não a conclui nem a apaga.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.nota_daily import NotaDaily
from app.models.usuario import Usuario
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou
from app.services.inadimplencia_service import hoje_brasilia

_TAMANHO_MAXIMO = 4000
_LIMITE_HISTORICO = 30


def _exigir_gestor(usuario: Usuario) -> None:
    if usuario.papel not in ("admin", "super_admin"):
        raise NaoAutorizado("As anotações da daily são do gestor (admin).")


def _nota_do_autor(db: Session, usuario: Usuario, nota_id: int) -> NotaDaily:
    nota = db.query(NotaDaily).filter_by(id=nota_id, tenant_id=usuario.tenant_id, autor_usuario_id=usuario.id).one_or_none()
    if nota is None:
        raise NaoEncontrado("Anotação não encontrada.")
    return nota


def _serializar(nota: NotaDaily) -> dict:
    return {"id": nota.id, "texto": nota.texto, "exibir_em": nota.exibir_em, "concluida_em": nota.concluida_em, "criado_em": nota.criado_em}


def criar(db: Session, usuario: Usuario, texto: str, exibir_em: date | None = None, hoje: date | None = None) -> dict:
    _exigir_gestor(usuario)
    hoje = hoje or hoje_brasilia()
    texto = (texto or "").strip()
    if not texto:
        raise ValidacaoFalhou("Escreva a anotação antes de salvar.")
    if len(texto) > _TAMANHO_MAXIMO:
        raise ValidacaoFalhou(f"A anotação aceita até {_TAMANHO_MAXIMO} caracteres.")
    exibir_em = exibir_em or (hoje + timedelta(days=1))
    if exibir_em < hoje:
        raise ValidacaoFalhou("Escolha hoje ou uma data futura para a anotação aparecer.")
    nota = NotaDaily(tenant_id=usuario.tenant_id, autor_usuario_id=usuario.id, texto=texto, exibir_em=exibir_em)
    db.add(nota)
    db.commit()
    db.refresh(nota)
    return _serializar(nota)


def listar(db: Session, usuario: Usuario, hoje: date | None = None) -> dict:
    """`destaque`: chegou a data e ainda não foi vista. `agendadas`: data futura. `historico`: as últimas vistas."""
    _exigir_gestor(usuario)
    hoje = hoje or hoje_brasilia()
    base = db.query(NotaDaily).filter_by(tenant_id=usuario.tenant_id, autor_usuario_id=usuario.id)
    pendentes = base.filter(NotaDaily.concluida_em.is_(None)).order_by(NotaDaily.exibir_em, NotaDaily.id).all()
    historico = (base.filter(NotaDaily.concluida_em.isnot(None)).order_by(NotaDaily.concluida_em.desc(), NotaDaily.id.desc())
                 .limit(_LIMITE_HISTORICO).all())
    return {
        "hoje": hoje,
        "destaque": [_serializar(n) for n in pendentes if n.exibir_em <= hoje],
        "agendadas": [_serializar(n) for n in pendentes if n.exibir_em > hoje],
        "historico": [_serializar(n) for n in historico],
    }


def concluir(db: Session, usuario: Usuario, nota_id: int, concluida: bool = True) -> dict:
    _exigir_gestor(usuario)
    nota = _nota_do_autor(db, usuario, nota_id)
    nota.concluida_em = datetime.now(UTC).replace(tzinfo=None) if concluida else None
    db.commit()
    db.refresh(nota)
    return _serializar(nota)


def excluir(db: Session, usuario: Usuario, nota_id: int) -> None:
    _exigir_gestor(usuario)
    db.delete(_nota_do_autor(db, usuario, nota_id))
    db.commit()
