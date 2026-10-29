import logging

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import rls
from app.models.notificacao_rede_social import NotificacaoRedeSocial
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider

logger = logging.getLogger(__name__)

_LIMITE_PADRAO = 50


def criar(db: Session, tenant_id: str, tipo: str, referencia_tipo: str, referencia_id: int, mensagem: str) -> None:
    """Helper interno de wiring (master prompt §65) — chamado de dentro
    de outras transações (solicitar_conexao, responder_conexao, comentar,
    reagir, enviar_mensagem); não comita, o `flush` garante o id/ordem
    sem fechar a transação de quem chamou.

    A notificação quase sempre é para OUTRA empresa (quem comentou avisa o dono do post). No PostgreSQL o RLS (D-111) deixa qualquer empresa inserir e só o dono ler,
    mas `INSERT ... RETURNING` exigiria também a política de leitura; por isso o insert é de Core, sem RETURNING (ninguém precisa do id aqui)."""
    # SQL direto, não `insert()` do SQLAlchemy: no PostgreSQL ele acrescenta `RETURNING id` sozinho, e o `RETURNING` exige a política de leitura da linha da outra empresa.
    db.execute(
        text(
            "INSERT INTO notificacao_rede_social (tenant_id, tipo, referencia_tipo, referencia_id, mensagem) "
            "VALUES (:tenant_id, :tipo, :referencia_tipo, :referencia_id, :mensagem)"
        ),
        {"tenant_id": tenant_id, "tipo": tipo, "referencia_tipo": referencia_tipo, "referencia_id": referencia_id, "mensagem": mensagem},
    )


def enviar_email_para_tenant(db: Session, email_provider: EmailProvider | None, tenant_id: str, mensagem: str) -> None:
    """Espelha toda notificação da Rede Social também por e-mail, pra todos
    os usuários ativos do tenant destino (a notificação em si é por
    `tenant_id`, sem `usuario_id` — não há como saber quem "é" o
    destinatário além de "todo mundo daquele tenant"). Chamado sempre
    depois do `db.commit()` da ação de negócio que originou a notificação
    (mesmo padrão de `pagamento_licenca_service`) — best-effort, uma falha
    de envio nunca pode reverter algo que já aconteceu."""
    if email_provider is None:
        return
    # Ler os e-mails dos usuários de OUTRA empresa é uma tarefa de sistema nomeada (o RLS esconde os usuários de outros tenants de quem está no contexto de tenant).
    with rls.contexto_sistema(db, "shoal-notificar-por-email"):
        destinatarios = [u.email for u in db.query(Usuario).filter(Usuario.tenant_id == tenant_id, Usuario.ativo.is_(True)).all()]
    for email_destino in destinatarios:
        try:
            email_provider.enviar(
                email_destino,
                "Nova notificação na B2B ON",
                mensagem,
                "B2B ON",
                settings.sendgrid_remetente_email,
                tenant_id,
            )
        except Exception:
            logger.warning(
                "Falha ao enviar e-mail de notificação da Rede Social pro tenant %s", tenant_id, exc_info=True
            )


def _serializar(notificacao: NotificacaoRedeSocial) -> dict:
    return {
        "id": notificacao.id,
        "tipo": notificacao.tipo,
        "referencia_tipo": notificacao.referencia_tipo,
        "referencia_id": notificacao.referencia_id,
        "mensagem": notificacao.mensagem,
        "lida": notificacao.lida_em is not None,
        "criado_em": notificacao.criado_em,
    }


def listar(db: Session, tenant_id: str, limite: int = _LIMITE_PADRAO) -> list[dict]:
    notificacoes = (
        db.query(NotificacaoRedeSocial)
        .filter_by(tenant_id=tenant_id)
        .order_by(NotificacaoRedeSocial.criado_em.desc(), NotificacaoRedeSocial.id.desc())
        .limit(limite)
        .all()
    )
    return [_serializar(notificacao) for notificacao in notificacoes]


def marcar_lida(db: Session, tenant_id: str, notificacao_id: int) -> None:
    notificacao = db.query(NotificacaoRedeSocial).filter_by(id=notificacao_id, tenant_id=tenant_id).one_or_none()
    if notificacao is None:
        return
    if notificacao.lida_em is None:
        notificacao.lida_em = func.now()
        db.commit()


def marcar_todas_lidas(db: Session, tenant_id: str) -> None:
    (
        db.query(NotificacaoRedeSocial)
        .filter_by(tenant_id=tenant_id, lida_em=None)
        .update({"lida_em": func.now()})
    )
    db.commit()


def contar_nao_lidas(db: Session, tenant_id: str) -> int:
    return db.query(func.count(NotificacaoRedeSocial.id)).filter_by(tenant_id=tenant_id, lida_em=None).scalar() or 0
