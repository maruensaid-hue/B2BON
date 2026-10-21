"""Pacotes adicionais de créditos de enriquecimento: catálogo versionado e aprovado, compra pelo checkout existente (Mercado Pago), crédito só pelo
webhook assinado, validade no fim do mês e rentabilidade calculada com o custo vigente.

Regras (matriz do PO, 2026-10-21):
  - o saldo comprado é separado da franquia (`origem=compra` no razão), NÃO aumenta nenhum limite do plano (decisores por empresa, créditos por
    pesquisa) e expira no fim do mês-calendário de Brasília, sem acumular;
  - a data de expiração é informada ANTES da compra: o catálogo traz `expira_em_previsto`, o pedido guarda o que foi informado e a compra exige o
    aceite explícito (`aceite_expiracao`);
  - total do pacote = créditos × preço unitário, em centavos pela regra do produto (`precos.centavos`, meio para cima); o catálogo só aceita preço
    total coerente com isso;
  - acima de 3.000 créditos (`CONTACT_SALES`) não tem preço nem checkout automático: só cotação comercial;
  - sem a pesquisa de decisores liberada (plano, política do provedor e orçamento global aprovados) a compra é recusada: não se vende crédito que
    não pode ser usado."""

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, ledger, precos
from app.models.enriquecimento_creditos import EnriquecimentoCompra, EnriquecimentoLoteCompra, EnriquecimentoPacote
from app.providers.payment.base import PaymentProvider
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, PesquisaBloqueada, ValidacaoFalhou

logger = logging.getLogger("b2bon.enriquecimento")

PREFIXO_REFERENCIA = "enriquecimento:"
STATUS_PACOTE = ("ATIVO", "CONTACT_SALES", "INATIVO")
TOLERANCIA_VALOR = Decimal("0.01")
_PENDENTES_DO_PROVEDOR = ("pending", "in_process", "authorized")  # o pagamento ainda pode ser aprovado: a compra continua PENDENTE


# ------------------------------------------------------------------------------------------------------------------------------- catálogo


def _vigente_aprovado(db: Session, codigo: str) -> EnriquecimentoPacote | None:
    linhas = db.query(EnriquecimentoPacote).filter(EnriquecimentoPacote.codigo == codigo).order_by(EnriquecimentoPacote.versao.desc()).all()
    return next((p for p in linhas if p.aprovado_em is not None and p.valido_ate is None), None)


def pacotes_vigentes(db: Session) -> list[EnriquecimentoPacote]:
    """Versão aprovada e vigente de cada pacote, em ordem de exibição (pacotes INATIVO ficam de fora)."""
    codigos = [c for (c,) in db.query(EnriquecimentoPacote.codigo).distinct().all()]
    vigentes = [p for p in (_vigente_aprovado(db, c) for c in codigos) if p is not None and p.status != "INATIVO"]
    return sorted(vigentes, key=lambda p: (p.ordem, p.codigo))


def _serializar(pacote: EnriquecimentoPacote) -> dict:
    checkout = pacote.status == "ATIVO"
    return {
        "codigo": pacote.codigo, "versao": pacote.versao, "nome": pacote.nome, "creditos": pacote.quantidade_creditos, "status": pacote.status,
        "preco_unitario_brl": str(precos.exibir(pacote.preco_unitario_brl, 2)) if pacote.preco_unitario_brl is not None else None,
        "preco_total_brl": str(precos.centavos(pacote.preco_total_brl)) if pacote.preco_total_brl is not None else None,
        "checkout_automatico": checkout, "sob_negociacao": pacote.status == "CONTACT_SALES",
    }


def catalogo(db: Session, agora: datetime | None = None) -> dict:
    """Catálogo para exibição (site e plataforma): pacotes vigentes e a data em que um crédito comprado AGORA expira."""
    agora = agora or config.agora_utc()
    return {"pacotes": [_serializar(p) for p in pacotes_vigentes(db)], "expira_em_previsto": config.fim_do_mes(agora).isoformat(),
            "regras": {"saldo_separado_da_franquia": True, "aumenta_limites_do_plano": False, "expira_no_fim_do_mes": True, "acumula": False}}


def _validar(status: str, creditos, unitario, total) -> tuple[int | None, Decimal | None, Decimal | None]:
    if status not in STATUS_PACOTE:
        raise ValidacaoFalhou(f"status deve ser um de: {', '.join(STATUS_PACOTE)}.")
    if status == "CONTACT_SALES":
        if unitario is not None or total is not None:
            raise ValidacaoFalhou("Pacote sob negociação (acima de 3.000 créditos) não tem preço nem checkout automático.")
        return (creditos if creditos is None or (isinstance(creditos, int) and not isinstance(creditos, bool) and creditos > 0) else None), None, None
    if isinstance(creditos, bool) or not isinstance(creditos, int) or creditos <= 0:
        raise ValidacaoFalhou("A quantidade de créditos do pacote deve ser um inteiro positivo.")
    if unitario is None:
        raise ValidacaoFalhou("Informe o preço unitário do pacote.")
    unit = precos.dec(unitario)
    if unit <= 0:
        raise ValidacaoFalhou("O preço unitário deve ser positivo.")
    calculado = precos.centavos(Decimal(creditos) * unit)
    if total is None:
        return creditos, unit, calculado
    informado = precos.dec(total)
    if informado != calculado:
        raise ValidacaoFalhou(f"O preço total ({informado}) não confere com créditos × preço unitário ({calculado}).")
    return creditos, unit, calculado


def definir_pacote(db: Session, *, codigo: str, nome: str, quantidade_creditos, preco_unitario_brl, preco_total_brl=None, status: str = "ATIVO",
                   ordem: int = 0, ator_id: str | None, tenant_auditoria: str, motivo: str | None, aprovar: bool = False) -> EnriquecimentoPacote:
    """Nova versão PENDENTE de aprovação de um pacote (preço nunca é editado no lugar: o pedido congela versão e preço)."""
    if not codigo or not codigo.strip() or not nome or not nome.strip():
        raise ValidacaoFalhou("Informe o código e o nome do pacote.")
    creditos, unit, total = _validar(status, quantidade_creditos, preco_unitario_brl, preco_total_brl)
    anteriores = db.query(EnriquecimentoPacote).filter(EnriquecimentoPacote.codigo == codigo.strip()).order_by(EnriquecimentoPacote.versao.desc()).all()
    novo = EnriquecimentoPacote(codigo=codigo.strip(), versao=(anteriores[0].versao + 1) if anteriores else 1, nome=nome.strip(),
                                quantidade_creditos=creditos, preco_unitario_brl=unit, preco_total_brl=total, status=status, ordem=ordem,
                                motivo=motivo, criado_por=ator_id)
    db.add(novo)
    db.flush()
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_pacote_definido", "enriquecimento_pacote", novo.id, ator_id,
                                {"codigo": novo.codigo, "versao": novo.versao, "creditos": creditos, "preco_unitario_brl": str(unit) if unit else None,
                                 "preco_total_brl": str(total) if total else None, "status": status, "pendente_aprovacao": True, "motivo": motivo})
    db.commit()
    if aprovar:
        aprovar_pacote(db, novo.id, ator_id, tenant_auditoria)
    return novo


def aprovar_pacote(db: Session, pacote_id: int, ator_id: str | None, tenant_auditoria: str) -> EnriquecimentoPacote:
    linha = db.get(EnriquecimentoPacote, pacote_id)
    if linha is None:
        raise NaoEncontrado("Pacote não encontrado.")
    irmas = db.query(EnriquecimentoPacote).filter(EnriquecimentoPacote.codigo == linha.codigo).all()
    config._aprovar_linha(db, linha, irmas, ator_id, tenant_auditoria, "enriquecimento_pacote_aprovado", "enriquecimento_pacote",
                          {"codigo": linha.codigo, "status": linha.status})
    return linha


# ----------------------------------------------------------------------------------------------------------------------------- rentabilidade


def rentabilidade(db: Session, provedor: str) -> dict:
    """Margem de cada pacote com o custo VIGENTE: o da política aprovada do provedor; sem política aprovada, o do lote de compra mais recente
    (marcado como referência). Se a relação crédito do cliente × crédito do provedor ainda não foi aprovada, assume-se 1:1 e isso é informado
    (`premissa_fator`). Recalculada a cada leitura: novo aporte ou nova política mudam o resultado sem tocar nos pacotes."""
    politica, _ = config.politica_vigente(db, provedor)
    custo_provedor, origem_custo, fator, premissa = None, None, None, False
    if politica is not None and politica.custo_unitario_brl is not None:
        custo_provedor, origem_custo = politica.custo_unitario_brl, f"politica_v{politica.versao}"
        fator = politica.creditos_cliente_por_credito_provedor
    if custo_provedor is None:
        lote = db.query(EnriquecimentoLoteCompra).filter_by(provedor=provedor).order_by(EnriquecimentoLoteCompra.comprado_em.desc(),
                                                                                       EnriquecimentoLoteCompra.id.desc()).first()
        if lote is not None:
            custo_provedor, origem_custo = precos.dec(lote.custo_unitario_brl), f"lote_{lote.referencia}"
    if fator is None:
        fator, premissa = 1, True
    saida = {"provedor": provedor, "custo_unitario_provedor_brl": str(precos.exibir(custo_provedor, 5)) if custo_provedor is not None else None,
             "origem_custo": origem_custo, "creditos_cliente_por_credito_provedor": fator, "premissa_fator": premissa, "pacotes": []}
    for pacote in pacotes_vigentes(db):
        item = {"codigo": pacote.codigo, "creditos": pacote.quantidade_creditos, "status": pacote.status}
        if pacote.status == "ATIVO" and custo_provedor is not None:
            custo_cliente = precos.dec(custo_provedor) / Decimal(fator)  # custo de UM crédito do cliente
            venda = precos.dec(pacote.preco_unitario_brl)
            total_venda = precos.dec(pacote.preco_total_brl)
            total_custo = precos.valor(pacote.quantidade_creditos, custo_cliente)
            item.update({"preco_unitario_brl": str(precos.exibir(venda, 2)), "preco_total_brl": str(total_venda),
                         "custo_total_brl": str(precos.exibir(total_custo, 2)), "lucro_bruto_brl": str(precos.exibir(total_venda - total_custo, 2)),
                         "markup_percentual": str(precos.exibir(precos.markup_percentual(venda, custo_cliente), 1)),
                         "margem_bruta_percentual": str(precos.exibir(precos.margem_sobre_venda(venda, custo_cliente), 1))})
        saida["pacotes"].append(item)
    return saida


# ---------------------------------------------------------------------------------------------------------------------------------- compras


def serializar_compra(compra: EnriquecimentoCompra) -> dict:
    return {
        "id": compra.id, "pacote": compra.pacote_codigo, "pacote_versao": compra.pacote_versao, "creditos": compra.creditos,
        "preco_unitario_brl": str(precos.exibir(compra.preco_unitario_brl, 2)), "preco_total_brl": str(precos.centavos(compra.preco_total_brl)),
        "status": compra.status, "expira_em_previsto": compra.expira_em_previsto.isoformat(),
        "expira_em": compra.expira_em.isoformat() if compra.expira_em else None, "url_checkout": compra.url_checkout,
        "criado_em": compra.criado_em.isoformat() if compra.criado_em else None,
        "confirmado_em": compra.confirmado_em.isoformat() if compra.confirmado_em else None,
    }


def iniciar_compra(db: Session, tenant_id: str, pacote_codigo: str, *, aceite_expiracao: bool, payment_provider: PaymentProvider, email_pagador: str,
                   provider, ator_id: str | None, agora: datetime | None = None) -> EnriquecimentoCompra:
    """Pedido de compra com versão e preço congelados e checkout no Mercado Pago. Os créditos só entram pelo webhook assinado."""
    if not aceite_expiracao:
        raise ValidacaoFalhou("Confirme que está ciente de que os créditos adicionais expiram no fim do mês e não acumulam.")
    pacote = _vigente_aprovado(db, pacote_codigo)
    if pacote is None or pacote.status == "INATIVO":
        raise NaoEncontrado("Pacote não encontrado.")
    if pacote.status != "ATIVO" or not pacote.quantidade_creditos or pacote.preco_total_brl is None or pacote.preco_unitario_brl is None:
        raise ValidacaoFalhou("Este pacote é negociado com o comercial: peça uma cotação.")
    motivos = config.motivos_de_indisponibilidade(db, tenant_id, provider)
    if motivos:
        # Não vende crédito que não pode ser usado: a pesquisa de decisores está indisponível por algum dos motivos abaixo.
        raise PesquisaBloqueada("A compra de créditos de enriquecimento está indisponível agora: " + "; ".join(m["mensagem"] for m in motivos),
                                motivos[0]["codigo"], motivos)
    agora = agora or config.agora_utc()
    compra = EnriquecimentoCompra(
        tenant_id=tenant_id, pacote_id=pacote.id, pacote_codigo=pacote.codigo, pacote_versao=pacote.versao, creditos=pacote.quantidade_creditos,
        preco_unitario_brl=pacote.preco_unitario_brl, preco_total_brl=precos.centavos(pacote.preco_total_brl), expira_em_previsto=config.fim_do_mes(agora),
        status="PENDENTE", criado_por=ator_id,
    )
    db.add(compra)
    db.flush()
    preferencia = payment_provider.criar_preferencia(
        referencia_externa=f"{PREFIXO_REFERENCIA}{compra.id}",
        descricao=f"B2B ON — {compra.creditos} créditos de enriquecimento (valem até o fim do mês)",
        valor=float(compra.preco_total_brl), email_pagador=email_pagador,
    )
    compra.preferencia_id_externo, compra.url_checkout = preferencia.id_externo, preferencia.url_checkout
    auditoria_service.registrar(db, tenant_id, "enriquecimento_compra_iniciada", "enriquecimento_compra", compra.id, ator_id,
                                {"pacote": compra.pacote_codigo, "versao": compra.pacote_versao, "creditos": compra.creditos,
                                 "preco_total_brl": str(compra.preco_total_brl), "expira_em_previsto": compra.expira_em_previsto.isoformat()})
    db.commit()
    return compra


def listar_compras(db: Session, tenant_id: str, limite: int = 50) -> list[EnriquecimentoCompra]:
    return db.query(EnriquecimentoCompra).filter_by(tenant_id=tenant_id).order_by(EnriquecimentoCompra.id.desc()).limit(limite).all()


def confirmar_via_webhook(db: Session, payment_provider: PaymentProvider, pagamento_id_externo: str, agora: datetime | None = None
                          ) -> EnriquecimentoCompra | None:
    """Chamado depois da assinatura do webhook validada. Ignora pagamentos que não são de enriquecimento. Idempotente: webhook repetido não credita
    de novo (compra já decidida + `compra:<id>` no razão + `pagamento_id_externo` único). O valor pago precisa bater com o pedido (±1 centavo).
    A validade é o fim do mês da CONFIRMAÇÃO: quem paga na virada do mês recebe o mês inteiro em vez de um crédito que já nasceria vencido."""
    detalhe = payment_provider.buscar_pagamento(pagamento_id_externo)
    referencia = detalhe.referencia_externa or ""
    if not referencia.startswith(PREFIXO_REFERENCIA) or not referencia.removeprefix(PREFIXO_REFERENCIA).isdigit():
        return None
    compra = db.get(EnriquecimentoCompra, int(referencia.removeprefix(PREFIXO_REFERENCIA)))
    if compra is None or compra.status != "PENDENTE":
        return compra
    if detalhe.status in _PENDENTES_DO_PROVEDOR:
        return compra  # ainda não decidido (Pix/boleto): aguarda o próximo aviso do provedor
    agora = agora or config.agora_utc()
    ledger.travar_carteira(db, compra.tenant_id)
    outra = db.query(EnriquecimentoCompra).filter(EnriquecimentoCompra.pagamento_id_externo == detalhe.id_externo,
                                                  EnriquecimentoCompra.id != compra.id).first()
    if outra is not None:
        logger.error("ENRIQUECIMENTO_COMPRA_PAGAMENTO_REPETIDO compra=%s outra=%s pagamento=%s", compra.id, outra.id, detalhe.id_externo)
        return compra
    compra.pagamento_id_externo, compra.confirmado_em = detalhe.id_externo, agora
    if detalhe.status != "approved":
        compra.status = "REJEITADA"
    elif abs(precos.dec(detalhe.valor) - precos.dec(compra.preco_total_brl)) > TOLERANCIA_VALOR:
        compra.status = "REJEITADA"
        logger.error("ENRIQUECIMENTO_COMPRA_VALOR_DIVERGENTE compra=%s pago=%s esperado=%s", compra.id, detalhe.valor, compra.preco_total_brl)
    else:
        compra.expira_em = config.fim_do_mes(agora)
        movimento = ledger.conceder_compra(db, compra.tenant_id, compra.id, compra.creditos, compra.expira_em, compra.pacote_codigo, agora)
        compra.movimento_id = movimento.id
        compra.status = "APROVADA"
    auditoria_service.registrar(db, compra.tenant_id, "enriquecimento_compra_confirmada", "enriquecimento_compra", compra.id, None,
                                {"status": compra.status, "pagamento": detalhe.id_externo, "creditos": compra.creditos,
                                 "expira_em": compra.expira_em.isoformat() if compra.expira_em else None})
    db.commit()
    return compra
