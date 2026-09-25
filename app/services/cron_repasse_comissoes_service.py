import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.comissao_representante import ComissaoRepresentante
from app.models.representante import Representante
from app.providers.channels.email.base import EmailProvider
from app.providers.payout.base import PayoutProvider
from app.services import auditoria_service

logger = logging.getLogger(__name__)

# Abaixo disso, a comissão fica represada em "calculada" até acumular o
# suficiente — evita gerar um Pix de centavos a cada mensalidade pequena.
_VALOR_MINIMO_REPASSE = 10.0


def repassar_pendentes(db: Session, payout_provider: PayoutProvider, email_provider: EmailProvider) -> dict:
    """Roda 1x/mês (cron externo) — processa toda `ComissaoRepresentante`
    ainda `"calculada"`. Nunca re-tenta sozinha uma que `"falhou"`: fica
    visível pra intervenção manual, mesmo espírito de
    `pagamento_licenca_service.enviar_lembretes_cobranca` (idempotente,
    sem retry automático escondido)."""
    pendentes = (
        db.query(ComissaoRepresentante)
        .filter_by(status="calculada")
        .filter(ComissaoRepresentante.valor_comissao >= _VALOR_MINIMO_REPASSE)
        .all()
    )

    repassadas = 0
    falhas = 0
    for comissao in pendentes:
        representante = db.query(Representante).filter_by(id=comissao.representante_id).one_or_none()
        if representante is None:
            continue
        try:
            resultado = payout_provider.enviar_pix(
                representante.chave_pix,
                comissao.valor_comissao,
                referencia_externa=str(comissao.id),
                descricao=f"Comissão B2B ON — {representante.nome}",
            )
        except Exception as erro:
            resultado = None
            motivo_falha = str(erro)
        else:
            motivo_falha = resultado.motivo_falha

        if resultado is not None and resultado.sucesso:
            comissao.status = "paga"
            comissao.pago_em = datetime.now(UTC)
            repassadas += 1
        else:
            comissao.status = "falhou"
            comissao.motivo_falha = motivo_falha
            falhas += 1

        auditoria_service.registrar(
            db, comissao.tenant_id, "comissao_representante_repassada", "comissao_representante", comissao.id, None,
            {"status": comissao.status, "valor": comissao.valor_comissao},
        )
        _notificar_representante(db, email_provider, representante, comissao)

    db.commit()
    return {"repassadas": repassadas, "falhas": falhas, "total_processado": len(pendentes)}


def _notificar_representante(
    db: Session, email_provider: EmailProvider, representante: Representante, comissao: ComissaoRepresentante
) -> None:
    try:
        if comissao.status == "paga":
            assunto = "Comissão B2B ON repassada"
            corpo = (
                f"Olá, {representante.nome}!\n\n"
                f"Repassamos R${comissao.valor_comissao:.2f} de comissão referente a um cliente indicado por você.\n\n"
                f"Qualquer dúvida, fale com a gente em suporte@cyberfort.com.br."
            )
        else:
            assunto = "Não conseguimos repassar sua comissão B2B ON"
            corpo = (
                f"Olá, {representante.nome}!\n\n"
                f"Tentamos repassar R${comissao.valor_comissao:.2f} de comissão, mas não conseguimos "
                f"({comissao.motivo_falha or 'motivo não informado'}). Vamos verificar e retornar em breve."
            )
        email_provider.enviar(
            representante.email, assunto, corpo, "B2B ON", settings.sendgrid_remetente_email, comissao.tenant_id,
        )
    except Exception:
        logger.warning(
            "Falha ao notificar representante %s sobre comissão %s", representante.id, comissao.id, exc_info=True
        )
