"""Top-up de AI Credits e recarga automática (Fase 15).

Fluxo: pedido (versão e preço do pacote congelados) → checkout do
provedor de pagamento existente (Mercado Pago) → webhook assinado →
CREDIT_PURCHASED num lote TOPUP com validade → auditoria. Os créditos
nunca entram pela volta do navegador, só pelo webhook, e o webhook
duplicado não credita duas vezes.

Recarga automática só existe com consentimento explícito do admin. A
integração de cobrança atual (preferência avulsa do Mercado Pago) não
guarda cartão para cobrança sem o cliente presente: quando o saldo cai
abaixo do limiar, o sistema cria o pedido e avisa; o pagamento é
concluído pelo cliente (TD-076).
"""

import calendar
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.finops import carteira, catalogos
from app.contexts.finops.comercial import TipoLote
from app.models.creditos_ia import CompraCreditos
from app.providers.payment.base import PaymentProvider
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

logger = logging.getLogger("b2bon.creditos")
PREFIXO_REFERENCIA = "creditos:"


def somar_meses(data: datetime, meses: int) -> datetime:
    """Mesmo dia `meses` depois; dia inexistente no mês de destino vira o último (31/01 + 1 → 28/02)."""
    indice = data.month - 1 + meses
    ano, mes = data.year + indice // 12, indice % 12 + 1
    return data.replace(year=ano, month=mes, day=min(data.day, calendar.monthrange(ano, mes)[1]))


def compra_dict(compra: CompraCreditos) -> dict:
    return {
        "id": compra.id, "pacote": compra.pacote_codigo, "pacote_versao": compra.pacote_versao, "creditos": compra.creditos,
        "preco": float(compra.preco), "moeda": compra.moeda, "validade_meses": compra.validade_meses, "origem": compra.origem,
        "status": compra.status, "url_checkout": compra.url_checkout,
        "criado_em": compra.criado_em.isoformat() if compra.criado_em else None,
        "confirmado_em": compra.confirmado_em.isoformat() if compra.confirmado_em else None,
    }


def _novo_pedido(db: Session, tenant_id: str, pacote_codigo: str, origem: str, ator_id: str | None) -> CompraCreditos:
    pacote = catalogos.obter_pacote(db, pacote_codigo)
    if pacote.status != "ATIVO" or not pacote.creditos or pacote.preco is None:
        raise ValidacaoFalhou("Este pacote é negociado com o comercial (Enterprise).")
    compra = CompraCreditos(
        tenant_id=tenant_id, pacote_id=pacote.id, pacote_codigo=pacote.codigo, pacote_versao=pacote.versao, creditos=pacote.creditos,
        preco=pacote.preco, moeda=pacote.moeda, validade_meses=pacote.validade_meses, origem=origem, status="PENDENTE", criado_por=ator_id,
    )
    db.add(compra)
    db.flush()
    return compra


def gerar_checkout(db: Session, compra: CompraCreditos, payment_provider: PaymentProvider, email_pagador: str) -> CompraCreditos:
    if compra.status != "PENDENTE":
        raise ValidacaoFalhou("Esta compra não está pendente.")
    if not compra.url_checkout:
        preferencia = payment_provider.criar_preferencia(
            referencia_externa=f"{PREFIXO_REFERENCIA}{compra.id}",
            descricao=f"B2B ON AI Credits — {compra.pacote_codigo} ({compra.creditos:,} créditos)".replace(",", "."),
            valor=float(compra.preco), email_pagador=email_pagador,
        )
        compra.preferencia_id_externo = preferencia.id_externo
        compra.url_checkout = preferencia.url_checkout
    return compra


def iniciar(db: Session, tenant_id: str, pacote_codigo: str, payment_provider: PaymentProvider, email_pagador: str,
            ator_id: str | None) -> CompraCreditos:
    compra = _novo_pedido(db, tenant_id, pacote_codigo, "MANUAL", ator_id)
    gerar_checkout(db, compra, payment_provider, email_pagador)
    auditoria_service.registrar(db, tenant_id, "compra_creditos_iniciada", "compra_credito", compra.id, ator_id,
                                {"pacote": compra.pacote_codigo, "versao": compra.pacote_versao, "preco": float(compra.preco)})
    db.commit()
    return compra


def obter(db: Session, tenant_id: str, compra_id: int) -> CompraCreditos:
    compra = db.get(CompraCreditos, compra_id)
    if compra is None or compra.tenant_id != tenant_id:
        raise NaoEncontrado(f"Compra {compra_id} não encontrada.")
    return compra


def listar(db: Session, tenant_id: str) -> list[CompraCreditos]:
    return db.query(CompraCreditos).filter_by(tenant_id=tenant_id).order_by(CompraCreditos.id.desc()).limit(50).all()


def confirmar_via_webhook(db: Session, payment_provider: PaymentProvider, pagamento_id_externo: str) -> CompraCreditos | None:
    """Chamado depois da assinatura do webhook validada. Ignora pagamentos
    que não são de créditos (licenças seguem o fluxo próprio)."""
    detalhe = payment_provider.buscar_pagamento(pagamento_id_externo)
    referencia = detalhe.referencia_externa or ""
    if not referencia.startswith(PREFIXO_REFERENCIA):
        return None
    compra = db.get(CompraCreditos, int(referencia.removeprefix(PREFIXO_REFERENCIA)))
    if compra is None or compra.status != "PENDENTE":
        return compra  # idempotente: webhook repetido não credita de novo
    carteira.travar(db, compra.tenant_id)
    compra.pagamento_id_externo = detalhe.id_externo
    compra.confirmado_em = datetime.now(UTC)
    if detalhe.status != "approved":
        compra.status = "REJEITADA"
    elif abs(Decimal(str(detalhe.valor)) - Decimal(str(compra.preco))) > Decimal("0.01"):
        compra.status = "REJEITADA"
        logger.error("CREDITOS_COMPRA_VALOR_DIVERGENTE compra=%s pago=%s esperado=%s", compra.id, detalhe.valor, compra.preco)
    else:
        agora = carteira.agora_utc()
        lote = carteira.conceder(
            db, compra.tenant_id, TipoLote.TOPUP, compra.creditos, f"PACOTE:{compra.pacote_codigo}", referencia=str(compra.id),
            expira_em=somar_meses(agora, compra.validade_meses) if compra.validade_meses else None,
            receita_por_credito=Decimal(str(compra.preco)) / compra.creditos, idempotency_key=f"compra:{compra.id}",
            descricao=f"Compra {compra.pacote_codigo} v{compra.pacote_versao}",
        )
        compra.lote_id = lote.id
        compra.status = "APROVADA"
    auditoria_service.registrar(db, compra.tenant_id, "compra_creditos_confirmada", "compra_credito", compra.id, None,
                                {"status": compra.status, "pagamento": detalhe.id_externo, "creditos": compra.creditos})
    db.commit()
    return compra


def configurar_recarga(db: Session, tenant_id: str, ativa: bool, limiar: int | None, pacote_codigo: str | None,
                       consentimento: bool, ator_id: str | None) -> dict:
    """Ativar exige consentimento explícito (registrado com quem e quando)."""
    config = carteira.configuracao(db, tenant_id)
    anterior = {"ativa": config.recarga_ativa, "limiar": config.recarga_limiar, "pacote": config.recarga_pacote_codigo}
    if ativa:
        if not consentimento:
            raise ValidacaoFalhou("A recarga automática só é ativada com o seu consentimento explícito.")
        if not limiar or limiar <= 0 or not pacote_codigo:
            raise ValidacaoFalhou("Informe o limiar e o pacote da recarga automática.")
        pacote = catalogos.obter_pacote(db, pacote_codigo)
        if pacote.status != "ATIVO":
            raise ValidacaoFalhou("Pacote indisponível para recarga automática.")
        config.recarga_ativa, config.recarga_limiar, config.recarga_pacote_codigo = True, limiar, pacote_codigo
        config.recarga_consentido_por, config.recarga_consentido_em = ator_id, datetime.now(UTC)
    else:
        config.recarga_ativa = False
    auditoria_service.registrar(db, tenant_id, "recarga_automatica_configurada", "configuracao_credito_tenant", config.id, ator_id,
                                {"valor_anterior": anterior, "valor_novo": {"ativa": config.recarga_ativa, "limiar": config.recarga_limiar,
                                                                            "pacote": config.recarga_pacote_codigo}})
    db.commit()
    return recarga_dict(config)


def recarga_dict(config) -> dict:
    return {"ativa": config.recarga_ativa, "limiar": config.recarga_limiar, "pacote": config.recarga_pacote_codigo,
            "consentido_por": config.recarga_consentido_por,
            "consentido_em": config.recarga_consentido_em.isoformat() if config.recarga_consentido_em else None}


def verificar_recarga_automatica(db: Session, tenant_id: str) -> CompraCreditos | None:
    """Saldo abaixo do limiar + consentimento → pedido de recarga (um por vez)."""
    config = carteira.configuracao(db, tenant_id)
    if not (config.recarga_ativa and config.recarga_consentido_em and config.recarga_limiar and config.recarga_pacote_codigo):
        return None
    if carteira.disponivel(db, tenant_id) >= Decimal(config.recarga_limiar):
        return None
    pendente = db.query(CompraCreditos).filter_by(tenant_id=tenant_id, origem="AUTO_RECARGA", status="PENDENTE").first()
    if pendente is not None:
        return None
    compra = _novo_pedido(db, tenant_id, config.recarga_pacote_codigo, "AUTO_RECARGA", config.recarga_consentido_por)
    auditoria_service.registrar(db, tenant_id, "recarga_automatica_disparada", "compra_credito", compra.id, None,
                                {"limiar": config.recarga_limiar, "pacote": compra.pacote_codigo})
    logger.info("CREDITOS_RECARGA_AUTOMATICA tenant=%s compra=%s", tenant_id, compra.id)
    db.commit()
    return compra
