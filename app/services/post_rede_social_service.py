from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.comentario_post import ComentarioPost
from app.models.perfil_empresa import PerfilEmpresa
from app.models.post_rede_social import PostRedeSocial
from app.models.reacao_post import ReacaoPost
from app.models.usuario import Usuario
from app.services import auditoria_service, midia_service, notificacao_rede_social_service
from app.services.errors import NaoAutorizado, NaoEncontrado, ValidacaoFalhou

_LIMITE_FEED_PADRAO = 50
_LIMITE_COMENTARIOS_PADRAO = 200


def criar(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    texto: str,
    imagem_url: str | None,
    link_url: str | None,
    *,
    midia_conteudo: bytes | None = None,
    midia_tipo_mime: str | None = None,
) -> dict:
    midia_conteudo_final: bytes | None = None
    midia_tipo_mime_final: str | None = None
    if midia_conteudo is not None:
        if midia_tipo_mime in midia_service.TIPOS_IMAGEM_PERMITIDOS:
            midia_conteudo_final = midia_service.comprimir_imagem(midia_conteudo)
            midia_tipo_mime_final = "image/jpeg"
        elif midia_tipo_mime in midia_service.TIPOS_VIDEO_PERMITIDOS:
            midia_conteudo_final = midia_service.comprimir_video(midia_conteudo)
            midia_tipo_mime_final = "video/mp4"
        else:
            raise ValidacaoFalhou(f"Tipo de arquivo não suportado: {midia_tipo_mime}. Envie uma foto ou um vídeo.")

    post = PostRedeSocial(
        tenant_id=tenant_id,
        usuario_autor_id=int(ator_id) if ator_id else None,
        texto=texto,
        imagem_url=imagem_url,
        link_url=link_url,
        midia_conteudo=midia_conteudo_final,
        midia_tipo_mime=midia_tipo_mime_final,
        midia_tamanho_bytes=len(midia_conteudo_final) if midia_conteudo_final is not None else None,
    )
    db.add(post)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "post_rede_social_criado", "post_rede_social", post.id, ator_id, {})
    db.commit()
    db.refresh(post)
    return _serializar(db, post, tenant_id_atual=tenant_id)


def obter_midia(db: Session, post_id: int) -> PostRedeSocial:
    post = _obter(db, post_id)
    if post.midia_conteudo is None:
        raise NaoEncontrado(f"Post {post_id} não tem mídia anexada")
    return post


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
    # Sem isso, comentário/reação ficam órfãos (post_id apontando pra um
    # post que não existe mais) — achado real testando E2E: o `id`
    # (INTEGER PRIMARY KEY sem AUTOINCREMENT) pode ser reciclado pelo
    # SQLite, e um post novo "herdava" comentários/reações de um post
    # antigo já excluído que por coincidência tinha o mesmo id.
    db.query(ComentarioPost).filter_by(post_id=post.id).delete()
    db.query(ReacaoPost).filter_by(post_id=post.id).delete()
    db.delete(post)
    db.commit()


def _serializar(db: Session, post: PostRedeSocial, tenant_id_atual: str | None) -> dict:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=post.tenant_id).one_or_none()
    autor = db.query(Usuario).filter_by(id=post.usuario_autor_id).one_or_none()
    total_comentarios = db.query(func.count(ComentarioPost.id)).filter_by(post_id=post.id).scalar() or 0
    total_reacoes = db.query(func.count(ReacaoPost.id)).filter_by(post_id=post.id).scalar() or 0
    eu_reagi = (
        tenant_id_atual is not None
        and db.query(ReacaoPost).filter_by(post_id=post.id, tenant_id=tenant_id_atual).one_or_none() is not None
    )
    return {
        "id": post.id,
        "tenant_id": post.tenant_id,
        "empresa_nome": perfil.nome_exibicao if perfil is not None else post.tenant_id,
        "empresa_logo_url": perfil.logo_url if perfil is not None else None,
        "autor_nome": autor.nome if autor is not None else "Usuário removido",
        "texto": post.texto,
        "imagem_url": post.imagem_url,
        "link_url": post.link_url,
        "midia_url": f"/rede-social/posts/{post.id}/midia" if post.midia_conteudo is not None else None,
        "midia_tipo": (
            ("video" if (post.midia_tipo_mime or "").startswith("video/") else "imagem")
            if post.midia_conteudo is not None
            else None
        ),
        "criado_em": post.criado_em,
        "total_comentarios": total_comentarios,
        "total_reacoes": total_reacoes,
        "eu_reagi": eu_reagi,
    }


def listar_feed(db: Session, tenant_id_atual: str | None = None, limite: int = _LIMITE_FEED_PADRAO) -> list[dict]:
    """Feed cronológico (master prompt §44) — todos os tenants, mais
    recente primeiro. Ranking por ICP Fit/Intent/Relationship/Trust é
    Fase 3 (depende de sinais que ainda não existem); aqui é
    estrutural, sem fingir uma IA de ranking que não existe ainda."""
    # `id.desc()` como critério de desempate — `criado_em` pode colidir
    # no mesmo segundo (granularidade do timestamp do banco), e sem isso
    # a ordem entre posts criados quase juntos fica indefinida.
    posts = db.query(PostRedeSocial).order_by(PostRedeSocial.criado_em.desc(), PostRedeSocial.id.desc()).limit(limite).all()
    return [_serializar(db, post, tenant_id_atual) for post in posts]


def _serializar_comentario(db: Session, comentario: ComentarioPost) -> dict:
    perfil = db.query(PerfilEmpresa).filter_by(tenant_id=comentario.tenant_id).one_or_none()
    autor = db.query(Usuario).filter_by(id=comentario.usuario_id).one_or_none()
    return {
        "id": comentario.id,
        "post_id": comentario.post_id,
        "tenant_id": comentario.tenant_id,
        "empresa_nome": perfil.nome_exibicao if perfil is not None else comentario.tenant_id,
        "autor_nome": autor.nome if autor is not None else "Usuário removido",
        "texto": comentario.texto,
        "criado_em": comentario.criado_em,
    }


def comentar(db: Session, tenant_id: str, ator_id: str, post_id: int, texto: str) -> dict:
    post = _obter(db, post_id)
    comentario = ComentarioPost(post_id=post_id, tenant_id=tenant_id, usuario_id=int(ator_id), texto=texto)
    db.add(comentario)
    db.flush()

    auditoria_service.registrar(
        db, tenant_id, "post_rede_social_comentado", "comentario_post", comentario.id, ator_id, {"post_id": post_id}
    )
    if post.tenant_id != tenant_id:
        perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
        nome = perfil.nome_exibicao if perfil is not None else tenant_id
        notificacao_rede_social_service.criar(
            db, post.tenant_id, "new_comment", "post_rede_social", post.id, f"{nome} comentou no seu post."
        )
    db.commit()
    db.refresh(comentario)
    return _serializar_comentario(db, comentario)


def listar_comentarios(db: Session, post_id: int, limite: int = _LIMITE_COMENTARIOS_PADRAO) -> list[dict]:
    _obter(db, post_id)
    comentarios = (
        db.query(ComentarioPost)
        .filter_by(post_id=post_id)
        .order_by(ComentarioPost.criado_em.asc(), ComentarioPost.id.asc())
        .limit(limite)
        .all()
    )
    return [_serializar_comentario(db, comentario) for comentario in comentarios]


def reagir(db: Session, tenant_id: str, ator_id: str, post_id: int) -> dict:
    """Toggle de reação (master prompt §45) — tipo único ("curtir"),
    1 reação por tenant por post: cria se não existe, remove se já existe."""
    post = _obter(db, post_id)
    reacao = db.query(ReacaoPost).filter_by(post_id=post_id, tenant_id=tenant_id).one_or_none()
    if reacao is None:
        reacao = ReacaoPost(post_id=post_id, tenant_id=tenant_id, usuario_id=int(ator_id))
        db.add(reacao)
        db.flush()
        auditoria_service.registrar(
            db, tenant_id, "post_rede_social_reagido", "reacao_post", reacao.id, ator_id, {"post_id": post_id}
        )
        if post.tenant_id != tenant_id:
            perfil = db.query(PerfilEmpresa).filter_by(tenant_id=tenant_id).one_or_none()
            nome = perfil.nome_exibicao if perfil is not None else tenant_id
            notificacao_rede_social_service.criar(
                db, post.tenant_id, "new_reaction", "post_rede_social", post.id, f"{nome} reagiu ao seu post."
            )
        reagiu = True
    else:
        auditoria_service.registrar(
            db, tenant_id, "post_rede_social_reacao_removida", "reacao_post", reacao.id, ator_id, {"post_id": post_id}
        )
        db.delete(reacao)
        db.flush()
        reagiu = False
    db.commit()

    total = db.query(func.count(ReacaoPost.id)).filter_by(post_id=post_id).scalar() or 0
    return {"reagiu": reagiu, "total": total}
