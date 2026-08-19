import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.providers.payment.base import PaymentProvider
from app.services import auditoria_service, webhook_parceiro_service
from app.services.errors import NaoEncontrado

_DIAS_LICENCA_POR_PAGAMENTO = 30


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


def confirmar_via_webhook(db: Session, payment_provider: PaymentProvider, pagamento_id_externo: str) -> None:
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

    if pagamento.status == "aprovado":
        licenca = db.query(Licenca).filter_by(tenant_id=pagamento.tenant_id).one_or_none()
        if licenca is None:
            licenca = Licenca(tenant_id=pagamento.tenant_id, plano_id=pagamento.plano_id, status="ativa")
            db.add(licenca)
        licenca.plano_id = pagamento.plano_id
        licenca.status = "ativa"
        licenca.data_expiracao = datetime.now(UTC) + timedelta(days=_DIAS_LICENCA_POR_PAGAMENTO)

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
    db.commit()


def status_licenca(db: Session, tenant_id: str) -> str:
    if db.query(Tenant).filter_by(id=tenant_id).one_or_none() is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
    licenca = db.query(Licenca).filter_by(tenant_id=tenant_id).one_or_none()
    if licenca is None:
        return "sem_licenca"
    return licenca.status
