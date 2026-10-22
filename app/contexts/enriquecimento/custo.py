"""Custo contratual do provedor, validação do contrato e conciliação financeira com o provedor.

Base econômica (informada pelo PO, 2026-10-21; nada daqui é estimado): custo mensal USD 600; 81.600 créditos por ano ⇒ referência mensal de 6.800;
custo unitário nominal USD 0,088235294; câmbio de PLANEJAMENTO R$ 6,00 ⇒ R$ 0,529411765 por crédito e R$ 3.600,00 por mês. O câmbio de planejamento serve
à precificação; o custo contábil de cada pagamento é o que foi efetivamente pago (`registrar_pagamento`: USD, taxa efetivamente aplicada e encargos
efetivamente cobrados). Nenhum imposto, encargo ou câmbio real é inventado.

Como o custo mensal é fixo, o custo POR CRÉDITO CONSUMIDO sobe com a ociosidade: `custo_efetivo` informa créditos consumidos, ociosos (que expiram no fim
do ciclo) e `custo mensal efetivo ÷ créditos realmente consumidos`.

Estes números são decisões comerciais já aprovadas pelo PO: não dependem de nova aprovação nem de "validação de contrato". O que o sistema confere sozinho,
com os dados que o próprio provedor devolve, é a **medição** (`billing.creditsCharged` de cada resposta), a **conciliação** com `GET /v3/account/usage` e a
capacidade (créditos totais informados pelo provedor × créditos anuais do contrato)."""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.enriquecimento import config, ledger, precos
from app.models.enriquecimento_creditos import EnriquecimentoCustoProvedor, EnriquecimentoPagamentoProvedor
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

logger = logging.getLogger("b2bon.enriquecimento")

@dataclass(frozen=True)
class CustoResolvido:
    id: int
    versao: int
    provedor: str
    custo_mensal_usd: Decimal
    creditos_anuais: int
    creditos_mensais: int
    cambio_planejamento_brl: Decimal
    custo_unitario_usd: Decimal
    custo_unitario_brl: Decimal
    custo_mensal_brl: Decimal


def _resolvido(linha: EnriquecimentoCustoProvedor) -> CustoResolvido:
    return CustoResolvido(
        id=linha.id, versao=linha.versao, provedor=linha.provedor, custo_mensal_usd=precos.dec(linha.custo_mensal_usd),
        creditos_anuais=linha.creditos_anuais, creditos_mensais=linha.creditos_mensais,
        cambio_planejamento_brl=precos.dec(linha.cambio_planejamento_brl), custo_unitario_usd=precos.dec(linha.custo_unitario_usd),
        custo_unitario_brl=precos.dec(linha.custo_unitario_brl), custo_mensal_brl=precos.dec(linha.custo_mensal_brl),
    )


def custo_vigente(db: Session, provedor: str) -> CustoResolvido | None:
    """Versão APROVADA e vigente do custo do provedor (ou None)."""
    linhas = db.query(EnriquecimentoCustoProvedor).filter_by(provedor=provedor).order_by(EnriquecimentoCustoProvedor.versao.desc()).all()
    aprovada = next((c for c in linhas if c.aprovado_em is not None and c.valido_ate is None), None)
    return _resolvido(aprovada) if aprovada is not None else None


def capacidade_mensal(db: Session, provedor: str) -> int | None:
    """Créditos do provedor por mês que o contrato comporta (None = custo ainda não configurado)."""
    custo = custo_vigente(db, provedor)
    return custo.creditos_mensais if custo is not None else None


def exigir_limite_dentro_da_capacidade(db: Session, provedor: str, limite_creditos: int | None) -> None:
    """Orçamento global em créditos nunca pode passar do que o contrato comporta por mês (a capacidade equivalente ao teto de custo)."""
    capacidade = capacidade_mensal(db, provedor)
    if capacidade is not None and limite_creditos is not None and limite_creditos > capacidade:
        raise ValidacaoFalhou(f"O orçamento global ({limite_creditos} créditos/mês) excede a capacidade do contrato ({capacidade} créditos/mês).")


def _positivo(nome: str, valor) -> Decimal:
    if isinstance(valor, bool) or valor is None:
        raise ValidacaoFalhou(f"{nome} é obrigatório.")
    try:
        numero = precos.dec(valor)
    except Exception:  # noqa: BLE001 - qualquer texto inválido vira erro de validação
        raise ValidacaoFalhou(f"{nome} deve ser um número decimal.") from None
    if not numero.is_finite() or numero <= 0:
        raise ValidacaoFalhou(f"{nome} deve ser positivo.")
    return numero


def definir_custo(db: Session, *, provedor: str, custo_mensal_usd, creditos_anuais, cambio_planejamento_brl, ator_id: str | None, tenant_auditoria: str,
                  motivo: str, aprovar: bool = False) -> EnriquecimentoCustoProvedor:
    """Nova versão PENDENTE do custo contratual. Todo valor vem de quem cadastra; os derivados são calculados aqui com `Decimal`."""
    if not motivo or not motivo.strip():
        raise ValidacaoFalhou("Informe o motivo.")
    usd = _positivo("custo_mensal_usd", custo_mensal_usd)
    cambio = _positivo("cambio_planejamento_brl", cambio_planejamento_brl)
    if isinstance(creditos_anuais, bool) or not isinstance(creditos_anuais, int) or creditos_anuais <= 0:
        raise ValidacaoFalhou("creditos_anuais deve ser um inteiro positivo.")
    if creditos_anuais % 12 != 0:
        raise ValidacaoFalhou("creditos_anuais deve ser divisível por 12 para a referência mensal equivalente.")
    mensais = creditos_anuais // 12
    unit_usd = precos.interna(usd / Decimal(mensais))
    unit_brl = precos.interna(usd * cambio / Decimal(mensais))
    anteriores = db.query(EnriquecimentoCustoProvedor).filter_by(provedor=provedor).order_by(EnriquecimentoCustoProvedor.versao.desc()).all()
    nova = EnriquecimentoCustoProvedor(
        provedor=provedor, versao=(anteriores[0].versao + 1) if anteriores else 1, custo_mensal_usd=usd, creditos_anuais=creditos_anuais,
        creditos_mensais=mensais, cambio_planejamento_brl=cambio, custo_unitario_usd=unit_usd, custo_unitario_brl=unit_brl,
        custo_mensal_brl=precos.centavos(usd * cambio), motivo=motivo.strip(), criado_por=ator_id,
    )
    db.add(nova)
    db.flush()
    auditoria_service.registrar(
        db, tenant_auditoria, "enriquecimento_custo_definido", "enriquecimento_custo_provedor", nova.id, ator_id,
        {"provedor": provedor, "versao": nova.versao, "custo_mensal_usd": str(usd), "creditos_anuais": creditos_anuais, "creditos_mensais": mensais,
         "cambio_planejamento_brl": str(cambio), "custo_unitario_brl": str(unit_brl), "motivo": motivo.strip(), "pendente_aprovacao": True},
    )
    db.commit()
    if aprovar:
        aprovar_custo(db, nova.id, ator_id, tenant_auditoria)
    return nova


def aprovar_custo(db: Session, custo_id: int, ator_id: str | None, tenant_auditoria: str) -> EnriquecimentoCustoProvedor:
    linha = db.get(EnriquecimentoCustoProvedor, custo_id)
    if linha is None:
        raise NaoEncontrado("Custo do provedor não encontrado.")
    orcamento = config.orcamento_vigente(db, linha.provedor)
    if orcamento.limite_creditos is not None and orcamento.limite_creditos > linha.creditos_mensais:
        raise ValidacaoFalhou(f"O orçamento global vigente ({orcamento.limite_creditos} créditos/mês) excede a capacidade desta versão do contrato "
                              f"({linha.creditos_mensais}). Reduza o orçamento antes.")
    irmas = db.query(EnriquecimentoCustoProvedor).filter_by(provedor=linha.provedor).all()
    config._aprovar_linha(db, linha, irmas, ator_id, tenant_auditoria, "enriquecimento_custo_aprovado", "enriquecimento_custo_provedor",
                          {"provedor": linha.provedor, "custo_unitario_brl": str(linha.custo_unitario_brl)})
    return linha


def registrar_pagamento(db: Session, *, provedor: str, referencia: str, periodo: str, valor_usd, taxa_cambio_efetiva, encargos_brl=0,
                        pago_em: datetime, observacao: str | None, ator_id: str | None, tenant_auditoria: str) -> EnriquecimentoPagamentoProvedor:
    """Pagamento efetivo ao provedor: USD pago, taxa de câmbio EFETIVAMENTE aplicada e encargos efetivamente cobrados (informados, nunca estimados).
    O valor em reais é `USD × taxa + encargos`, em centavos. Append-only; mesma referência duas vezes é recusada."""
    if not referencia or not referencia.strip():
        raise ValidacaoFalhou("Informe a referência do pagamento (fatura ou comprovante).")
    if len(periodo or "") != 7 or periodo[4] != "-" or not (periodo[:4] + periodo[5:]).isdigit() or not 1 <= int(periodo[5:]) <= 12:
        raise ValidacaoFalhou("O período deve estar no formato AAAA-MM.")
    usd, taxa = _positivo("valor_usd", valor_usd), _positivo("taxa_cambio_efetiva", taxa_cambio_efetiva)
    encargos = precos.dec(encargos_brl or 0)
    if encargos < 0:
        raise ValidacaoFalhou("Os encargos não podem ser negativos.")
    if db.query(EnriquecimentoPagamentoProvedor).filter_by(provedor=provedor, referencia=referencia.strip()).first() is not None:
        raise ValidacaoFalhou("Já existe um pagamento com essa referência.")
    pagamento = EnriquecimentoPagamentoProvedor(
        provedor=provedor, referencia=referencia.strip(), periodo=periodo, valor_usd=usd, taxa_cambio_efetiva=taxa, encargos_brl=precos.centavos(encargos),
        valor_brl_total=precos.centavos(usd * taxa + encargos), pago_em=pago_em, observacao=observacao, registrado_por=ator_id,
    )
    db.add(pagamento)
    db.flush()
    auditoria_service.registrar(db, tenant_auditoria, "enriquecimento_pagamento_provedor_registrado", "enriquecimento_pagamento_provedor", pagamento.id,
                                ator_id, {"provedor": provedor, "periodo": periodo, "valor_usd": str(usd), "taxa_cambio_efetiva": str(taxa),
                                          "valor_brl_total": str(pagamento.valor_brl_total)})
    db.commit()
    return pagamento


def custo_efetivo(db: Session, provedor: str, periodo: str) -> dict:
    """Custo do ciclo e custo por crédito CONSUMIDO. Usa os pagamentos efetivos do período quando existirem; senão o custo de planejamento (e diz isso).
    `ociosos` são os créditos do ciclo que não foram consumidos (e, sem transferência de saldo, expiram)."""
    custo = custo_vigente(db, provedor)
    consumidos = ledger.consumo_provedor(db, provedor, periodo)
    pagamentos = db.query(EnriquecimentoPagamentoProvedor).filter_by(provedor=provedor, periodo=periodo).all()
    if custo is None:
        return {"provedor": provedor, "periodo": periodo, "configurado": False, "creditos_consumidos": consumidos}
    efetivo = sum((precos.dec(p.valor_brl_total) for p in pagamentos), Decimal(0)) if pagamentos else None
    base = efetivo if efetivo is not None else custo.custo_mensal_brl
    ociosos = max(0, custo.creditos_mensais - consumidos)
    por_credito = precos.interna(base / Decimal(consumidos)) if consumidos > 0 else None
    return {
        "provedor": provedor, "periodo": periodo, "configurado": True,
        "custo_mensal_planejamento_brl": str(custo.custo_mensal_brl), "custo_mensal_efetivo_brl": str(efetivo) if efetivo is not None else None,
        "base_do_calculo": "pagamentos_efetivos" if efetivo is not None else "planejamento",
        "custo_unitario_nominal_brl": str(custo.custo_unitario_brl), "custo_unitario_nominal_usd": str(custo.custo_unitario_usd),
        "cambio_planejamento_brl": str(custo.cambio_planejamento_brl), "creditos_referencia_mes": custo.creditos_mensais,
        "creditos_consumidos": consumidos, "creditos_ociosos": ociosos,
        "ociosidade_percentual": str(precos.exibir(Decimal(ociosos) * 100 / Decimal(custo.creditos_mensais), 1)),
        "custo_efetivo_por_credito_consumido_brl": str(por_credito) if por_credito is not None else None,
        "pagamentos": [{"referencia": p.referencia, "valor_usd": str(p.valor_usd), "taxa_cambio_efetiva": str(p.taxa_cambio_efetiva),
                        "encargos_brl": str(p.encargos_brl), "valor_brl_total": str(p.valor_brl_total), "pago_em": p.pago_em} for p in pagamentos],
        "aviso": None if efetivo is not None else "Sem pagamento registrado neste período: o custo mensal é o de planejamento (câmbio de planejamento), não o contábil.",
    }

