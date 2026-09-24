from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conta import Conta
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.decisor import Decisor
from app.models.email_direto import EmailDireto
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.services import atividade_service, auditoria_service, comunicacao_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada


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

    resultado = email_provider.enviar(
        destinatario=decisor.email,
        assunto=assunto,
        corpo=corpo_final,
        remetente_nome=remetente_nome,
        remetente_email=remetente_email,
        tenant_id=tenant_id,
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


def listar_enviados(db: Session, tenant_id: str, usuario_atual: Usuario, conta_id: int | None = None) -> list[dict]:
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


def obter_configuracao(usuario: Usuario) -> dict:
    return {"email_nome_exibicao": usuario.email_nome_exibicao, "email_assinatura": usuario.email_assinatura}


def atualizar_configuracao(
    db: Session, usuario: Usuario, email_nome_exibicao: str | None, email_assinatura: str | None
) -> dict:
    usuario.email_nome_exibicao = email_nome_exibicao
    usuario.email_assinatura = email_assinatura
    db.commit()
    return obter_configuracao(usuario)
