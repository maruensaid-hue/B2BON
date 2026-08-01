import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.aprovacao import Aprovacao
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

VARIAVEIS_PERMITIDAS = {"nome", "empresa", "cargo"}
_PADRAO_VARIAVEL = re.compile(r"\{\{(\w+)\}\}")


def criar_proposta(
    db: Session,
    tenant_id: str,
    cadencia_id: int,
    decisor_id: int,
    canal: str,
    template_id: str | None,
    conteudo: str,
    toque_cadencia_id: int | None = None,
) -> Mensagem:
    """Cria uma mensagem proposta e a correspondente entrada na fila.

    Chamada pelo `cadencia_service` (E3-H1) para cada toque personalizado.
    """
    mensagem = Mensagem(
        tenant_id=tenant_id,
        cadencia_id=cadencia_id,
        decisor_id=decisor_id,
        canal=canal,
        template_id=template_id,
        conteudo=conteudo,
        toque_cadencia_id=toque_cadencia_id,
        status="aguardando_aprovacao",
    )
    db.add(mensagem)
    db.flush()

    aprovacao = Aprovacao(tenant_id=tenant_id, mensagem_id=mensagem.id, status="pendente")
    db.add(aprovacao)
    db.flush()

    auditoria_service.registrar(db, tenant_id, "mensagem_proposta", "mensagem", mensagem.id, None, {}, canal=canal)
    db.commit()
    db.refresh(mensagem)
    return mensagem


def _conta_id_da_mensagem(db: Session, mensagem: Mensagem) -> int:
    decisor = db.query(Decisor).filter_by(id=mensagem.decisor_id).one()
    return decisor.conta_id


def listar_fila(
    db: Session,
    tenant_id: str,
    canal: str | None = None,
    conta_id: int | None = None,
    cadencia_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    """Fila com filtros por canal, conta e cadência (E4-H1)."""
    query = (
        db.query(Aprovacao, Mensagem, Decisor)
        .join(Mensagem, Aprovacao.mensagem_id == Mensagem.id)
        .join(Decisor, Mensagem.decisor_id == Decisor.id)
        .filter(Aprovacao.tenant_id == tenant_id)
    )
    if canal:
        query = query.filter(Mensagem.canal == canal)
    if conta_id:
        query = query.filter(Decisor.conta_id == conta_id)
    if cadencia_id:
        query = query.filter(Mensagem.cadencia_id == cadencia_id)
    if status:
        query = query.filter(Aprovacao.status == status)

    return [
        {
            "aprovacao_id": aprovacao.id,
            "status": aprovacao.status,
            "mensagem_id": mensagem.id,
            "canal": mensagem.canal,
            "template_id": mensagem.template_id,
            "conteudo": mensagem.conteudo,
            "cadencia_id": mensagem.cadencia_id,
            "conta_id": decisor.conta_id,
            "decisor_id": decisor.id,
            "criado_em": mensagem.criado_em,
        }
        for aprovacao, mensagem, decisor in query.all()
    ]


def _obter_aprovacao(db: Session, tenant_id: str, aprovacao_id: int) -> Aprovacao:
    aprovacao = db.query(Aprovacao).filter_by(id=aprovacao_id, tenant_id=tenant_id).one_or_none()
    if aprovacao is None:
        raise NaoEncontrado(f"Aprovação {aprovacao_id} não encontrada")
    return aprovacao


def aprovar(db: Session, tenant_id: str, ator_id: str | None, aprovacao_id: int) -> Aprovacao:
    aprovacao = _obter_aprovacao(db, tenant_id, aprovacao_id)
    mensagem = db.query(Mensagem).filter_by(id=aprovacao.mensagem_id).one()

    aprovacao.status = "aprovado"
    aprovacao.aprovador_id = ator_id
    aprovacao.decidido_em = datetime.now(UTC)
    mensagem.status = "aprovado"

    auditoria_service.registrar(
        db,
        tenant_id,
        "aprovacao_aprovada",
        "aprovacao",
        aprovacao.id,
        ator_id,
        {},
        conta_id=_conta_id_da_mensagem(db, mensagem),
        canal=mensagem.canal,
    )
    db.commit()
    db.refresh(aprovacao)
    return aprovacao


def aprovar_lote(db: Session, tenant_id: str, ator_id: str | None, aprovacao_ids: list[int]) -> list[Aprovacao]:
    """Aprovação em lote só é permitida para itens do mesmo template (E4-H1)."""
    aprovacoes = [_obter_aprovacao(db, tenant_id, aid) for aid in aprovacao_ids]
    mensagens = [db.query(Mensagem).filter_by(id=a.mensagem_id).one() for a in aprovacoes]

    templates = {m.template_id for m in mensagens}
    if len(templates) > 1:
        raise ValidacaoFalhou("Aprovação em lote só é permitida para itens do mesmo template.")

    agora = datetime.now(UTC)
    for aprovacao, mensagem in zip(aprovacoes, mensagens, strict=True):
        aprovacao.status = "aprovado"
        aprovacao.aprovador_id = ator_id
        aprovacao.decidido_em = agora
        mensagem.status = "aprovado"
        auditoria_service.registrar(
            db,
            tenant_id,
            "aprovacao_aprovada_lote",
            "aprovacao",
            aprovacao.id,
            ator_id,
            {},
            conta_id=_conta_id_da_mensagem(db, mensagem),
            canal=mensagem.canal,
        )

    db.commit()
    for aprovacao in aprovacoes:
        db.refresh(aprovacao)
    return aprovacoes


def rejeitar(db: Session, tenant_id: str, ator_id: str | None, aprovacao_id: int, motivo: str | None) -> Aprovacao:
    aprovacao = _obter_aprovacao(db, tenant_id, aprovacao_id)
    mensagem = db.query(Mensagem).filter_by(id=aprovacao.mensagem_id).one()

    aprovacao.status = "rejeitado"
    aprovacao.aprovador_id = ator_id
    aprovacao.decidido_em = datetime.now(UTC)

    auditoria_service.registrar(
        db,
        tenant_id,
        "aprovacao_rejeitada",
        "aprovacao",
        aprovacao.id,
        ator_id,
        {"motivo": motivo},
        conta_id=_conta_id_da_mensagem(db, mensagem),
        canal=mensagem.canal,
    )
    db.commit()
    db.refresh(aprovacao)
    return aprovacao


def editar_mensagem(
    db: Session, tenant_id: str, ator_id: str | None, aprovacao_id: int, novo_conteudo: str
) -> Mensagem:
    """Edição inline preservando variáveis de personalização válidas (E4-H2)."""
    aprovacao = _obter_aprovacao(db, tenant_id, aprovacao_id)
    if aprovacao.status not in ("pendente", "editado"):
        raise RegraNegocioViolada("Só é possível editar mensagens ainda não aprovadas/rejeitadas.")

    mensagem = db.query(Mensagem).filter_by(id=aprovacao.mensagem_id).one()

    variaveis_novas = set(_PADRAO_VARIAVEL.findall(novo_conteudo))
    invalidas = variaveis_novas - VARIAVEIS_PERMITIDAS
    if invalidas:
        raise ValidacaoFalhou(f"Variáveis de personalização inválidas: {', '.join(sorted(invalidas))}")

    conteudo_anterior = mensagem.conteudo
    mensagem.conteudo = novo_conteudo
    aprovacao.status = "editado"

    auditoria_service.registrar(
        db,
        tenant_id,
        "mensagem_editada",
        "mensagem",
        mensagem.id,
        ator_id,
        {"conteudo_anterior": conteudo_anterior, "conteudo_novo": novo_conteudo},
        conta_id=_conta_id_da_mensagem(db, mensagem),
        canal=mensagem.canal,
    )
    db.commit()
    db.refresh(mensagem)
    return mensagem


def marcar_enviada(db: Session, tenant_id: str, mensagem_id: int) -> Mensagem:
    """Guarda: nenhuma mensagem é enviada sem estado 'aprovado' (E4-H1).

    O envio real pertence ao E3 (Onda 2); esta função existe para que o
    critério seja verificado por teste automatizado já nesta onda.
    """
    mensagem = db.query(Mensagem).filter_by(id=mensagem_id, tenant_id=tenant_id).one_or_none()
    if mensagem is None:
        raise NaoEncontrado(f"Mensagem {mensagem_id} não encontrada")

    aprovacao = (
        db.query(Aprovacao)
        .filter_by(mensagem_id=mensagem.id)
        .order_by(Aprovacao.id.desc())
        .first()
    )
    if aprovacao is None or aprovacao.status != "aprovado":
        raise RegraNegocioViolada("Mensagem não pode ser enviada sem estar aprovada.")

    mensagem.status = "enviado"
    mensagem.enviado_em = datetime.now(UTC)
    auditoria_service.registrar(
        db,
        tenant_id,
        "mensagem_enviada",
        "mensagem",
        mensagem.id,
        None,
        {},
        conta_id=_conta_id_da_mensagem(db, mensagem),
        canal=mensagem.canal,
    )
    db.commit()
    db.refresh(mensagem)
    return mensagem
