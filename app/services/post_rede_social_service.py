from sqlalchemy.orm import Session

from app.models.perfil_empresa import PerfilEmpresa
from app.models.post_rede_social import PostRedeSocial
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import NaoAutorizado, NaoEncontrado

_LIMITE_FEED_PADRAO = 50


def criar(
    db: Session, tenant_id: str, ator_id: str | None, texto: str, imagem_url: str | None, link_url: str | None
) -> dict:
    post = PostRedeSocial(
        tenant_id=tenant_id,
        usuario_autor_id=int(ator_id) if ator_id else None,
        texto=texto,
        imagem_url=imagem_url,
        link_url=link_url,
    )
    db.add(post)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "post_rede_social_criado", "post_rede_social", post.id, ator_id, {})
    db.commit()
    db.refresh(post)
    return _serializar(db, post)


def _obter(db: Session, post_id: int) -> PostRedeSocial:
    post = db.query(PostRedeSocial).filter_by(id=post_id).one_or_none()
    if post is None:
        raise NaoEncontrado(f"Post {post_id} não encontrado")
    return post


def excluir(db: Session, tenant_id: str, ator_id: str | None, post_id: int) -> None:
    post = _obter(db, post_id)
    if post.tenant_id != tenant_id:
        raise NaoAutorizado("Só a própria empresa autora pode excluir este post.")

    auditoria_service.registrar(db, tenant_id, "post_rede_social_excluido", "post_rede_social", post.id, ator_id, {})
    db.delete(post)
    db.commit()


def _serializar(db: Session, post: PostRedeSocial) -> dict:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=post.tenant_id).one_or_none()
    autor = db.query(Usuario).filter_by(id=post.usuario_autor_id).one_or_none()
    return {
        "id": post.id,
        "tenant_id": post.tenant_id,
        "empresa_nome": perfil.nome_exibicao if perfil is not None else post.tenant_id,
        "empresa_logo_url": perfil.logo_url if perfil is not None else None,
        "autor_nome": autor.nome if autor is not None else "Usuário removido",
        "texto": post.texto,
        "imagem_url": post.imagem_url,
        "link_url": post.link_url,
        "criado_em": post.criado_em,
    }


def listar_feed(db: Session, limite: int = _LIMITE_FEED_PADRAO) -> list[dict]:
    """Feed cronológico (master prompt §44) — todos os tenants, mais
    recente primeiro. Ranking por ICP Fit/Intent/Relationship/Trust é
    Fase 3 (depende de sinais que ainda não existem); aqui é
    estrutural, sem fingir uma IA de ranking que não existe ainda."""
    # `id.desc()` como critério de desempate — `criado_em` pode colidir
    # no mesmo segundo (granularidade do timestamp do banco), e sem isso
    # a ordem entre posts criados quase juntos fica indefinida.
    posts = db.query(PostRedeSocial).order_by(PostRedeSocial.criado_em.desc(), PostRedeSocial.id.desc()).limit(limite).all()
    return [_serializar(db, post) for post in posts]
