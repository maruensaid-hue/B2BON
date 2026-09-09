import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.providers.channels.email.base import EmailProvider
from app.providers.payment.base import PaymentProvider
from app.services import auditoria_service, webhook_parceiro_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada

logger = logging.getLogger(__name__)

_DIAS_LICENCA_POR_PAGAMENTO = 30
_DIAS_CARENCIA_PAGAMENTO = 3
_DIAS_AVISO_PRE_VENCIMENTO = 3


def iniciar(
    db: Session, tenant_id: str, plano_id: int, email_pagador: str, payment_provider: PaymentProvider
) -> tuple[PagamentoLicenca, str | None]:
    """Abre uma cobrança para formalizar a licença de um tenant recém-criado
    via cadastro self-service (convite-vitrine com escolha de plano).
    Devolve a URL de checkout junto — não é persistida (efêmera, só serve
    pra redirecionar o navegador logo em seguida). `None` quando o plano é
    gratuito (ver abaixo) — não há checkout pra redirecionar."""
    plano = db.query(Plano).filter_by(id=plano_id).one_or_none()
    if plano is None:
        raise NaoEncontrado(f"Plano {plano_id} não encontrado")

    if plano.preco_mensal <= 0:
        # Plano gratuito (ex.: POC) — o Mercado Pago recusa criar uma
        # preferência de cobrança de valor zero (400 Bad Request, raio-X
        # de produção real). Sem cobrança pra fazer, ativa a licença na
        # hora, sem passar pelo checkout.
        pagamento = PagamentoLicenca(
            tenant_id=tenant_id,
            plano_id=plano_id,
            preferencia_id_externo="",
            status="aprovado",
            valor=0,
            confirmado_em=datetime.now(UTC),
        )
        db.add(pagamento)
        db.flush()

        licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
        if licenca is None:
            licenca = Licenca(tenant_id=tenant_id, plano_id=plano_id, status="ativa")
            db.add(licenca)
        licenca.plano_id = plano_id
        licenca.status = "ativa"
        licenca.data_expiracao = datetime.now(UTC) + timedelta(days=_DIAS_LICENCA_POR_PAGAMENTO)

        auditoria_service.registrar(
            db, tenant_id, "pagamento_licenca_gratuito_ativado", "pagamento_licenca", pagamento.id, None,
            {"plano_id": plano_id},
        )
        db.commit()
        db.refresh(pagamento)
        return pagamento, None

    pagamento = PagamentoLicenca(
        tenant_id=tenant_id, plano_id=plano_id, preferencia_id_externo="", status="pendente", valor=plano.preco_mensal
    )
    db.add(pagamento)
    db.flush()

    preferencia = payment_provider.criar_preferencia(
        referencia_externa=str(pagamento.id),
        descricao=f"B2B ON — Plano {plano.nome}",
        valor=plano.preco_mensal,
        email_pagador=email_pagador,
    )
    pagamento.preferencia_id_externo = preferencia.id_externo

    auditoria_service.registrar(
        db, tenant_id, "pagamento_licenca_iniciado", "pagamento_licenca", pagamento.id, None, {"plano_id": plano_id}
    )
    db.commit()
    db.refresh(pagamento)
    return pagamento, preferencia.url_checkout


def verificar_assinatura_webhook(
    x_signature: str | None, x_request_id: str | None, payment_id_query: str | None, secret: str
) -> bool:
    """Algoritmo documentado pelo Mercado Pago: HMAC-SHA256 sobre um
    manifest `id:<payment_id>;request-id:<x-request-id>;ts:<ts>;`, chave
    o "Secret Key" configurado no painel de Webhooks (diferente do Access
    Token). Sem isso, qualquer um poderia forjar um POST de "aprovado" e
    ganhar licença de graça — é por isso que isto roda antes de qualquer
    outra coisa no handler do webhook."""
    if not secret or not x_signature or not x_request_id or not payment_id_query:
        return False

    partes = dict(item.split("=", 1) for item in x_signature.split(",") if "=" in item)
    ts = partes.get("ts")
    v1_esperado = partes.get("v1")
    if not ts or not v1_esperado:
        return False

    manifest = f"id:{payment_id_query.lower()};request-id:{x_request_id};ts:{ts};"
    v1_calculado = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(v1_calculado, v1_esperado)


def confirmar_via_webhook(
    db: Session, payment_provider: PaymentProvider, pagamento_id_externo: str, email_provider: EmailProvider
) -> None:
    """Chamado só depois que a assinatura do webhook já foi validada pela
    rota. Idempotente: um webhook duplicado (o Mercado Pago reenvia em
    caso de timeout na resposta) não reprocessa nem re-estende a licença."""
    detalhe = payment_provider.buscar_pagamento(pagamento_id_externo)
    if not detalhe.referencia_externa:
        return

    pagamento = db.query(PagamentoLicenca).filter_by(id=int(detalhe.referencia_externa)).one_or_none()
    if pagamento is None:
        return
    if pagamento.confirmado_em is not None:
        return

    pagamento.pagamento_id_externo = detalhe.id_externo
    pagamento.status = "aprovado" if detalhe.status == "approved" else "rejeitado"
    pagamento.confirmado_em = datetime.now(UTC)

    licenca = None
    if pagamento.status == "aprovado":
        licenca = db.query(Licenca).filter_by(tenant_id=pagamento.tenant_id).one_or_none()
        if licenca is None:
            licenca = Licenca(tenant_id=pagamento.tenant_id, plano_id=pagamento.plano_id, status="ativa")
            db.add(licenca)
        licenca.plano_id = pagamento.plano_id
        licenca.status = "ativa"
        licenca.data_expiracao = datetime.now(UTC) + timedelta(days=_DIAS_LICENCA_POR_PAGAMENTO)
        # Confirmação de fato chegou — a carência da autodeclaração
        # (se houve uma) não é mais necessária.
        licenca.declaracao_pagamento_em = None

    auditoria_service.registrar(
        db,
        pagamento.tenant_id,
        "pagamento_licenca_confirmado",
        "pagamento_licenca",
        pagamento.id,
        None,
        {"status": pagamento.status},
    )
    if pagamento.status == "aprovado":
        webhook_parceiro_service.enfileirar_evento(
            db, pagamento.tenant_id, "pagamento_confirmado",
            {"tenant_id": pagamento.tenant_id, "plano_id": pagamento.plano_id, "valor": pagamento.valor},
        )
        _enviar_email_agradecimento(db, email_provider, pagamento, licenca)
    db.commit()


def _destinatarios_admin(db: Session, tenant_id: str) -> list[Usuario]:
    return db.query(Usuario).filter(Usuario.tenant_id == tenant_id, Usuario.papel.in_(["admin", "super_admin"])).all()


def _enviar_email_agradecimento(
    db: Session, email_provider: EmailProvider, pagamento: PagamentoLicenca, licenca: Licenca
) -> None:
    tenant = db.query(Tenant).filter_by(id=pagamento.tenant_id).one_or_none()
    if tenant is None:
        return
    razao_social = tenant.razao_social
    data_expiracao = licenca.data_expiracao.strftime("%d/%m/%Y") if licenca.data_expiracao else ""
    for usuario in _destinatarios_admin(db, pagamento.tenant_id):
        try:
            corpo = (
                f"Olá, {usuario.nome}!\n\n"
                f"Recebemos a confirmação do pagamento da mensalidade da B2B ON ({razao_social}). "
                f"Muito obrigado por continuar com a gente!\n\n"
                f"Sua licença está ativa até {data_expiracao}, com acesso completo ao CRM, "
                f"prospecção automatizada e MAP (Motor de Alta Performance).\n\n"
                f"Qualquer dúvida, estamos à disposição em suporte@cyberfort.com.br."
            )
            email_provider.enviar(
                usuario.email, "Recebemos seu pagamento — obrigado!", corpo, "B2B ON",
                settings.sendgrid_remetente_email, pagamento.tenant_id,
            )
        except Exception:
            logger.warning(
                "Falha ao enviar e-mail de agradecimento pro tenant %s", pagamento.tenant_id, exc_info=True
            )


def status_licenca(db: Session, tenant_id: str) -> str:
    if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if licenca is None:
        return "sem_licenca"
    return licenca.status


def declarar_pagamento(db: Session, tenant_id: str) -> Licenca:
    """Autoatendimento "já paguei" (raio-X 2026-09-09) — reativa o acesso na
    hora pra quem foi suspenso mas já pagou e está esperando a compensação
    bancária (boleto ou cartão), sem precisar contactar o suporte. Abre uma
    carência própria de `_DIAS_CARENCIA_PAGAMENTO` a partir de agora
    (`suspender_licencas_vencidas` volta a suspender se o pagamento não for
    de fato confirmado dentro desse prazo)."""
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if licenca is None:
        raise NaoEncontrado("Licença não encontrada.")
    if licenca.status != "suspensa":
        raise RegraNegocioViolada("Só é possível declarar pagamento de uma licença suspensa.")

    licenca.status = "ativa"
    licenca.declaracao_pagamento_em = datetime.now(UTC)
    auditoria_service.registrar(db, tenant_id, "pagamento_declarado_pelo_usuario", "licenca", licenca.id, None, {})
    db.commit()
    db.refresh(licenca)
    return licenca


def enviar_lembretes_cobranca(db: Session, email_provider: EmailProvider) -> dict:
    """Cron entrypoint (`POST /cron/enviar-lembretes-cobranca`) — um aviso
    único 3 dias antes do vencimento, e um lembrete diário durante os 3
    dias de carência após o vencimento (mesma janela de
    `suspender_licencas_vencidas`). Só tenants `modo_cobranca == "direta"`
    — "consolidada" não tem vencimento próprio (ver `exigir_licenca_ativa`).
    `ultimo_lembrete_cobranca_em` evita reenviar se o cron rodar de novo no
    mesmo dia."""
    agora = datetime.now(UTC)
    hoje = agora.date()

    licencas = (
        db.query(Licenca)
        .join(Tenant, Tenant.id == Licenca.tenant_id)
        .filter(
            Licenca.status == "ativa",
            Licenca.data_expiracao.isnot(None),
            Tenant.modo_cobranca == "direta",
        )
        .all()
    )

    enviados = 0
    for licenca in licencas:
        if licenca.ultimo_lembrete_cobranca_em == hoje:
            continue

        dias_para_vencer = (licenca.data_expiracao.date() - hoje).days
        if dias_para_vencer == _DIAS_AVISO_PRE_VENCIMENTO:
            if _enviar_lembrete(db, email_provider, licenca, vencido=False):
                enviados += 1
                licenca.ultimo_lembrete_cobranca_em = hoje
        elif -_DIAS_CARENCIA_PAGAMENTO <= dias_para_vencer < 0:
            if _enviar_lembrete(db, email_provider, licenca, vencido=True):
                enviados += 1
                licenca.ultimo_lembrete_cobranca_em = hoje

    db.commit()
    return {"lembretes_enviados": enviados}


def _enviar_lembrete(db: Session, email_provider: EmailProvider, licenca: Licenca, vencido: bool) -> bool:
    tenant = db.query(Tenant).filter_by(id=licenca.tenant_id).one_or_none()
    if tenant is None:
        return False
    razao_social = tenant.razao_social
    data_vencimento = licenca.data_expiracao.strftime("%d/%m/%Y")
    destinatarios = _destinatarios_admin(db, licenca.tenant_id)
    if not destinatarios:
        return False

    for usuario in destinatarios:
        try:
            if vencido:
                data_limite = (licenca.data_expiracao + timedelta(days=_DIAS_CARENCIA_PAGAMENTO)).strftime("%d/%m/%Y")
                assunto = "Ainda não identificamos o pagamento da sua mensalidade B2B ON"
                corpo = (
                    f"Olá, {usuario.nome}!\n\n"
                    f"Ainda não identificamos o pagamento da mensalidade da B2B ON ({razao_social}), "
                    f"vencida em {data_vencimento}.\n\n"
                    f"Você tem até {data_limite} para regularizar sem perder o acesso. Se já pagou "
                    f"(boleto ou cartão) e o pagamento ainda está em compensação, use a opção "
                    f'"Já fiz o pagamento" dentro da plataforma — seu acesso volta na hora enquanto '
                    f"confirmamos.\n\n"
                    f"Para pagar ou revisar sua assinatura: {settings.url_base_frontend}/login"
                )
            else:
                assunto = "Sua mensalidade da B2B ON vence em 3 dias"
                corpo = (
                    f"Olá, {usuario.nome}!\n\n"
                    f"Sua mensalidade da B2B ON ({razao_social}) vence em 3 dias, no dia {data_vencimento}.\n\n"
                    f"Se você já pagou ou já tem o pagamento automático configurado, pode ignorar este "
                    f"e-mail. Caso ainda não tenha pago, acesse {settings.url_base_frontend}/login para "
                    f"regularizar.\n\n"
                    f"Qualquer dúvida, é só responder este e-mail ou falar com a gente em "
                    f"suporte@cyberfort.com.br."
                )
            email_provider.enviar(
                usuario.email, assunto, corpo, "B2B ON", settings.sendgrid_remetente_email, licenca.tenant_id,
            )
        except Exception:
            logger.warning("Falha ao enviar lembrete de cobrança pro tenant %s", licenca.tenant_id, exc_info=True)
    return True
