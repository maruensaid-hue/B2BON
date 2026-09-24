import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conta import Conta
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.decisor import Decisor
from app.models.email_direto import EmailDireto
from app.models.email_recebido import EmailRecebido
from app.models.negocio import Negocio
from app.models.estagio_funil import EstagioFunil
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.services import atividade_service, auditoria_service, comunicacao_service, resposta_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

logger = logging.getLogger(__name__)


def _obter_decisor(db: Session, tenant_id: str, decisor_id: int) -> Decisor:
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()
    if decisor is None:
        raise NaoEncontrado(f"Decisor {decisor_id} não encontrado")
    return decisor


def enviar(
    db: Session,
    tenant_id: str,
    ator: Usuario,
    decisor_id: int,
    assunto: str,
    corpo: str,
    email_provider: EmailProvider,
) -> dict:
    """Webmail — o vendedor já escreveu e revisou o texto sozinho, então
    o envio é síncrono, sem fila de aprovação (diferente de `Mensagem`/
    cadência). Reaproveita o MESMO provider (SendGrid/SMTP) já
    configurado pro tenant — nunca uma conta pessoal de Gmail/Outlook
    via OAuth, que não existe no projeto."""
    decisor = _obter_decisor(db, tenant_id, decisor_id)
    if not decisor.email:
        raise RegraNegocioViolada(f"O decisor {decisor.nome} não tem e-mail cadastrado.")
    conta = db.query(Conta).filter_by(id=decisor.conta_id).one()

    config_envio = db.query(ConfiguracaoEnvio).filter_by(tenant_id=tenant_id).one_or_none()
    remetente_nome = ator.email_nome_exibicao or ator.nome
    remetente_email = config_envio.remetente_email if config_envio else settings.sendgrid_remetente_email
    assinatura = ator.email_assinatura or (config_envio.assinatura if config_envio else "")

    corpo_final = f"{corpo}\n\n{assinatura}" if assinatura else corpo
    # Rodapé de opt-out sempre incluso (decisão confirmada com o usuário)
    # — mesma proteção de reputação/compliance das cadências, mesmo
    # sendo correspondência pessoal 1:1.
    corpo_final = comunicacao_service.rodape_email(tenant_id, decisor.id, corpo_final)

    # Caixa de entrada (raio-X 2026-09-24) — só troca o reply-to quando o
    # domínio de recebimento está configurado (`settings.dominio_
    # respostas`); sem isso, comportamento idêntico a antes (resposta cai
    # direto na caixa real do tenant, como sempre foi).
    reply_to = None
    if settings.dominio_respostas:
        token = resposta_service.gerar_token_resposta(tenant_id, decisor.id)
        reply_to = f"resp+{token}@{settings.dominio_respostas}"

    resultado = email_provider.enviar(
        destinatario=decisor.email,
        assunto=assunto,
        corpo=corpo_final,
        remetente_nome=remetente_nome,
        remetente_email=remetente_email,
        tenant_id=tenant_id,
        reply_to=reply_to,
    )

    email = EmailDireto(
        tenant_id=tenant_id,
        remetente_usuario_id=ator.id,
        decisor_id=decisor.id,
        conta_id=decisor.conta_id,
        assunto=assunto,
        # Guarda o texto EXATO que saiu (com assinatura + rodapé de
        # opt-out) — histórico de "enviados" mostra o e-mail de
        # verdade, não uma reconstrução parcial do que o vendedor
        # digitou originalmente.
        corpo=corpo_final,
        status="enviado" if resultado.sucesso else "falhou",
        motivo_falha=None if resultado.sucesso else resultado.motivo_falha,
        enviado_em=datetime.now(UTC) if resultado.sucesso else None,
    )
    db.add(email)
    db.flush()

    if resultado.sucesso:
        atividade_service.registrar(
            db,
            tenant_id,
            conta_id=decisor.conta_id,
            tipo="email",
            descricao=f"E-mail enviado: {assunto}",
            ator_id=str(ator.id),
        )
        auditoria_service.registrar(
            db,
            tenant_id,
            "email_direto_enviado",
            "email_direto",
            email.id,
            str(ator.id),
            {"decisor_id": decisor.id},
            conta_id=decisor.conta_id,
            canal="email",
        )

    db.commit()
    db.refresh(email)
    return {
        "id": email.id,
        "decisor_id": decisor.id,
        "decisor_nome": decisor.nome,
        "decisor_email": decisor.email,
        "conta_id": decisor.conta_id,
        "conta_nome": conta.nome,
        "remetente_usuario_id": ator.id,
        "remetente_nome": remetente_nome,
        "assunto": email.assunto,
        "corpo": email.corpo,
        "status": email.status,
        "motivo_falha": email.motivo_falha,
        "enviado_em": email.enviado_em,
        "criado_em": email.criado_em,
    }


def listar_enviados(
    db: Session,
    tenant_id: str,
    usuario_atual: Usuario,
    conta_id: int | None = None,
    incluir_arquivados: bool = False,
) -> list[dict]:
    """Vendedor comum só vê os próprios e-mails; admin/super_admin veem
    todos do tenant — mesmo espírito hierárquico já usado em outras
    telas (MAP, hierarquia de distribuidores)."""
    query = (
        db.query(EmailDireto, Decisor, Conta, Usuario)
        .join(Decisor, EmailDireto.decisor_id == Decisor.id)
        .join(Conta, EmailDireto.conta_id == Conta.id)
        .join(Usuario, EmailDireto.remetente_usuario_id == Usuario.id)
        .filter(EmailDireto.tenant_id == tenant_id)
    )
    if usuario_atual.papel not in ("admin", "super_admin"):
        query = query.filter(EmailDireto.remetente_usuario_id == usuario_atual.id)
    if conta_id:
        query = query.filter(EmailDireto.conta_id == conta_id)
    if not incluir_arquivados:
        query = query.filter(EmailDireto.arquivado_em.is_(None))
    query = query.order_by(EmailDireto.criado_em.desc())

    return [
        {
            "id": email.id,
            "decisor_id": decisor.id,
            "decisor_nome": decisor.nome,
            "decisor_email": decisor.email,
            "conta_id": conta.id,
            "conta_nome": conta.nome,
            "remetente_usuario_id": remetente.id,
            "remetente_nome": remetente.email_nome_exibicao or remetente.nome,
            "assunto": email.assunto,
            "corpo": email.corpo,
            "status": email.status,
            "motivo_falha": email.motivo_falha,
            "enviado_em": email.enviado_em,
            "criado_em": email.criado_em,
        }
        for email, decisor, conta, remetente in query.all()
    ]


def listar_recebidos(
    db: Session,
    tenant_id: str,
    usuario_atual: Usuario,
    conta_id: int | None = None,
    incluir_arquivados: bool = False,
) -> list[dict]:
    """Espelha `listar_enviados` — mesma hierarquia de visibilidade, mas
    escopada por `Decisor.criado_por`? Não: `EmailRecebido` não tem
    remetente_usuario_id (não foi ninguém do tenant que "enviou"), então
    a visibilidade por vendedor aqui é via `Conta.vendedor_usuario_id`
    (quem é dono da conta vê a resposta dela), não por quem mandou."""
    query = (
        db.query(EmailRecebido, Decisor, Conta)
        .outerjoin(Decisor, EmailRecebido.decisor_id == Decisor.id)
        .outerjoin(Conta, EmailRecebido.conta_id == Conta.id)
        .filter(EmailRecebido.tenant_id == tenant_id)
    )
    if usuario_atual.papel not in ("admin", "super_admin"):
        query = query.filter(Conta.vendedor_usuario_id == usuario_atual.id)
    if conta_id:
        query = query.filter(EmailRecebido.conta_id == conta_id)
    if not incluir_arquivados:
        query = query.filter(EmailRecebido.arquivado_em.is_(None))
    query = query.order_by(EmailRecebido.criado_em.desc())

    return [
        {
            "id": email.id,
            "decisor_id": decisor.id if decisor else None,
            "decisor_nome": decisor.nome if decisor else None,
            "conta_id": conta.id if conta else None,
            "conta_nome": conta.nome if conta else None,
            "remetente_email": email.remetente_email,
            "assunto": email.assunto,
            "corpo": email.corpo,
            "criado_em": email.criado_em,
        }
        for email, decisor, conta in query.all()
    ]


def processar_recebido(
    db: Session,
    tenant_id: str,
    decisor_id: int,
    remetente_email: str,
    assunto: str,
    corpo: str,
    email_provider: EmailProvider,
) -> EmailRecebido:
    """Chamado pelo webhook de Inbound Parse (`POST /webhooks/email/
    inbound`) já com `tenant_id`/`decisor_id` decodificados do token de
    resposta — nunca recebe o token bruto aqui. `decisor_id` continua
    sendo procurado (pode ter sido excluído depois do token ser
    gerado) — sem ele, ainda registra e retransmite (sabemos o tenant
    de qualquer forma, o token já garante isso), só sem vínculo."""
    decisor = db.query(Decisor).filter_by(id=decisor_id, tenant_id=tenant_id).one_or_none()

    email = EmailRecebido(
        tenant_id=tenant_id,
        decisor_id=decisor.id if decisor else None,
        conta_id=decisor.conta_id if decisor else None,
        remetente_email=remetente_email,
        assunto=assunto,
        corpo=corpo,
    )
    db.add(email)
    db.flush()

    if decisor:
        atividade_service.registrar(
            db, tenant_id, conta_id=decisor.conta_id, tipo="email", descricao=f"E-mail recebido: {assunto}"
        )
        # Já comita — cobre o `add` do EmailRecebido/Atividade acima
        # dentro da mesma transação.
        resposta_service.marcar_resposta(db, tenant_id, decisor.id)
    else:
        db.commit()
    db.refresh(email)

    _retransmitir_para_tenant(db, tenant_id, remetente_email, assunto, corpo, email_provider)
    return email


def _retransmitir_para_tenant(
    db: Session, tenant_id: str, remetente_email: str, assunto: str, corpo: str, email_provider: EmailProvider
) -> None:
    """Best-effort — nunca deixa o e-mail já persistido (visível no
    Webmail) virar erro 500 só porque a retransmissão falhou."""
    config_envio = db.query(ConfiguracaoEnvio).filter_by(tenant_id=tenant_id).one_or_none()
    destinatario = config_envio.remetente_email if config_envio else settings.sendgrid_remetente_email
    if not destinatario:
        return
    try:
        resultado = email_provider.enviar(
            destinatario=destinatario,
            assunto=f"Resposta via B2B ON: {assunto}",
            corpo=f"Resposta de {remetente_email}:\n\n{corpo}",
            remetente_nome=settings.sendgrid_remetente_nome,
            remetente_email=settings.sendgrid_remetente_email,
            tenant_id=tenant_id,
        )
        if not resultado.sucesso:
            logger.warning("Falha ao retransmitir resposta de e-mail pro tenant %s: %s", tenant_id, resultado.motivo_falha)
    except Exception:
        logger.warning("Erro ao retransmitir resposta de e-mail pro tenant %s", tenant_id, exc_info=True)


def listar_pendentes_arquivamento(db: Session, tenant_id: str, usuario_atual: Usuario) -> list[dict]:
    """Decisores com pelo menos 1 `EmailDireto`/`EmailRecebido` ainda não
    arquivado — alimenta a aba "Arquivar" do Webmail."""
    enviados = listar_enviados(db, tenant_id, usuario_atual, incluir_arquivados=False)
    recebidos = listar_recebidos(db, tenant_id, usuario_atual, incluir_arquivados=False)

    agrupado: dict[int, dict] = {}
    for item in enviados:
        grupo = agrupado.setdefault(
            item["decisor_id"],
            {
                "decisor_id": item["decisor_id"],
                "decisor_nome": item["decisor_nome"],
                "conta_nome": item["conta_nome"],
                "total_enviados": 0,
                "total_recebidos": 0,
            },
        )
        grupo["total_enviados"] += 1
    for item in recebidos:
        if item["decisor_id"] is None:
            continue
        grupo = agrupado.setdefault(
            item["decisor_id"],
            {
                "decisor_id": item["decisor_id"],
                "decisor_nome": item["decisor_nome"],
                "conta_nome": item["conta_nome"],
                "total_enviados": 0,
                "total_recebidos": 0,
            },
        )
        grupo["total_recebidos"] += 1

    return sorted(agrupado.values(), key=lambda item: item["decisor_nome"])


def arquivar_conversa(db: Session, tenant_id: str, ator: Usuario, decisor_id: int) -> dict:
    """Junta tudo ainda não arquivado daquele decisor (enviados +
    recebidos), marca com timestamp, e registra UMA `Atividade`
    consolidada na Conta e em cada Negócio ABERTO ligado a ela —
    negócios já ganhos/perdidos são encerrados, não precisam de
    registro novo de conversa ativa. Idempotente: rodar de novo só
    arquiva o que ficou pendente desde a última vez (sem pendências,
    não cria atividade nova)."""
    decisor = _obter_decisor(db, tenant_id, decisor_id)

    pendentes_enviados = (
        db.query(EmailDireto)
        .filter_by(tenant_id=tenant_id, decisor_id=decisor.id, arquivado_em=None)
        .all()
    )
    pendentes_recebidos = (
        db.query(EmailRecebido)
        .filter_by(tenant_id=tenant_id, decisor_id=decisor.id, arquivado_em=None)
        .all()
    )
    total = len(pendentes_enviados) + len(pendentes_recebidos)
    if total == 0:
        return {"enviados_arquivados": 0, "recebidos_arquivados": 0}

    agora = datetime.now(UTC)
    for email in pendentes_enviados:
        email.arquivado_em = agora
    for email in pendentes_recebidos:
        email.arquivado_em = agora

    descricao = f"Conversa arquivada com {decisor.nome} — {total} mensagem(ns)"
    atividade_service.registrar(
        db, tenant_id, conta_id=decisor.conta_id, tipo="email", descricao=descricao, ator_id=str(ator.id)
    )
    negocios_abertos = (
        db.query(Negocio)
        .join(EstagioFunil, Negocio.estagio_id == EstagioFunil.id)
        .filter(Negocio.tenant_id == tenant_id, Negocio.conta_id == decisor.conta_id, EstagioFunil.tipo == "aberto")
        .all()
    )
    for negocio in negocios_abertos:
        atividade_service.registrar(
            db, tenant_id, negocio_id=negocio.id, tipo="email", descricao=descricao, ator_id=str(ator.id)
        )

    auditoria_service.registrar(
        db,
        tenant_id,
        "email_conversa_arquivada",
        "decisor",
        decisor.id,
        str(ator.id),
        {"total": total},
        conta_id=decisor.conta_id,
        canal="email",
    )
    db.commit()
    return {"enviados_arquivados": len(pendentes_enviados), "recebidos_arquivados": len(pendentes_recebidos)}


def obter_configuracao(usuario: Usuario) -> dict:
    return {"email_nome_exibicao": usuario.email_nome_exibicao, "email_assinatura": usuario.email_assinatura}


def atualizar_configuracao(
    db: Session, usuario: Usuario, email_nome_exibicao: str | None, email_assinatura: str | None
) -> dict:
    usuario.email_nome_exibicao = email_nome_exibicao
    usuario.email_assinatura = email_assinatura
    db.commit()
    return obter_configuracao(usuario)
