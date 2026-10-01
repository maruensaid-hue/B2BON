"""Comissão Government (D-072, D-074): política por componente; o cálculo é do Commission Engine único
(`app/contexts/comissoes`), o mesmo das vendas privadas.

- Taxa e "comissionável" vêm do componente (cópia da política do contrato): licença e subscrição inicial 20%,
  renovações 10%, serviços e AI Credits adicionais 10%, implantação não comissionável por padrão.
- Gatilho PAYMENT_RECEIVED: cada recebimento é apurado (receita → impostos → infraestrutura → Margem Comissionável
  Líquida) e a comissão = margem × taxa × fração. Parcelas: proporcional ao que foi recebido.
- Estorno: comissão não paga é anulada; paga vira CLAWBACK negativo a compensar.
- Dono da comissão: o representante do contrato (ou a divisão configurada). Transferir a carteira muda só
  o futuro; comissões já geradas ficam com quem as gerou.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.comissoes import contract as comissoes
from app.contexts.governo.tipos import Componente
from app.models.comissao_representante import ComissaoRepresentante
from app.models.contrato_governo import ComponenteContratoGoverno, ContratoGoverno, PeriodoAssinaturaGoverno, RecebimentoGoverno
from app.models.plano import Plano
from app.models.representante import Representante
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou


def _beneficiarios(contrato: ContratoGoverno) -> list[tuple[int, Decimal]]:
    if contrato.divisao_comissao:
        return [(int(item["representante_id"]), Decimal(str(item["fracao"]))) for item in contrato.divisao_comissao]
    return [(contrato.representante_id, Decimal(1))] if contrato.representante_id else []


def _numero_renovacao(db: Session, componente: ComponenteContratoGoverno) -> int | None:
    if componente.tipo != Componente.RENOVACAO.value or componente.periodo_id is None:
        return None
    return db.get(PeriodoAssinaturaGoverno, componente.periodo_id).numero - 1


def _meses_operacao(db: Session, componente: ComponenteContratoGoverno, recebimento: RecebimentoGoverno) -> float:
    """D-076: meses de operação que o recebimento remunera — subscrição: meses do período × fração recebida do componente;
    licença, implantação e adicionais: 0 (o custo de infraestrutura do tenant-mês vai para a subscrição, uma vez)."""
    if componente.tipo not in comissoes.tipos.COMPONENTES_OPERACIONAIS or componente.periodo_id is None or not componente.valor:
        return 0.0
    periodo = db.get(PeriodoAssinaturaGoverno, componente.periodo_id)
    meses = (periodo.fim.year - periodo.inicio.year) * 12 + periodo.fim.month - periodo.inicio.month \
        + (periodo.fim.day - periodo.inicio.day) / 30
    return round(max(meses, 0) * float(recebimento.valor) / float(componente.valor), 4)


def reconhecer_recebimento(db: Session, contrato: ContratoGoverno, componente: ComponenteContratoGoverno,
                           recebimento: RecebimentoGoverno) -> list[ComissaoRepresentante]:
    """Todo recebimento é apurado (waterfall do MAP); só componente comissionável gera comissão."""
    comissionavel = componente.comissionavel and componente.taxa_comissao and not componente.cancelado
    plano = db.get(Plano, contrato.plano_id)
    tipo_receita = componente.tipo_receita or comissoes.tipos.TIPO_RECEITA_POR_COMPONENTE.get(componente.tipo) \
        or comissoes.tipos.RECEITA_NAO_CLASSIFICADA
    _, geradas = comissoes.motor.registrar_recebimento(
        db, origem=comissoes.tipos.Origem.RECEBIMENTO_GOVERNO, tenant_id=contrato.tenant_id, segmento="GOVERNMENT",
        produto=plano.nome if plano else "B2B ON Government", recebido_em=recebimento.recebido_em, receita_bruta=recebimento.valor,
        tipo_receita=tipo_receita, meses_infra=_meses_operacao(db, componente, recebimento),
        beneficiarios=_beneficiarios(contrato) if comissionavel else [], taxa=componente.taxa_comissao if comissionavel else None,
        recebimento_governo_id=recebimento.id, componente_tipo=componente.tipo,
        meta={"componente_governo_id": componente.id, "contrato_governo_id": contrato.id,
              "numero_renovacao": _numero_renovacao(db, componente)},
    )
    return geradas


def estornar_recebimento(db: Session, recebimento: RecebimentoGoverno) -> dict:
    return comissoes.motor.estornar(db, recebimento_governo_id=recebimento.id)


def _exigir_aprovacao(motivo: str | None, aprovado_por: str | None) -> None:
    if not (motivo or "").strip() or not (aprovado_por or "").strip():
        raise ValidacaoFalhou("Mudança de comissão exige motivo e aprovador.")


def alterar_componente(db: Session, componente_id: int, *, comissionavel: bool | None = None, taxa: float | None = None,
                       motivo: str, aprovado_por: str, ator_id: str | None) -> ComponenteContratoGoverno:
    """Override de comissão de um componente (vale para os próximos reconhecimentos)."""
    _exigir_aprovacao(motivo, aprovado_por)
    componente = db.get(ComponenteContratoGoverno, componente_id)
    if componente is None:
        raise NaoEncontrado(f"Componente {componente_id} não encontrado")
    novo_comissionavel = componente.comissionavel if comissionavel is None else comissionavel
    nova_taxa = componente.taxa_comissao if taxa is None else taxa
    if novo_comissionavel and (nova_taxa is None or not 0 < nova_taxa <= 1):
        raise ValidacaoFalhou("Componente comissionável precisa de taxa entre 0 e 1.")
    antes = {"comissionavel": componente.comissionavel, "taxa": componente.taxa_comissao}
    componente.comissionavel, componente.taxa_comissao = novo_comissionavel, nova_taxa
    contrato = db.get(ContratoGoverno, componente.contrato_id)
    auditoria_service.registrar(db, contrato.tenant_id, "comissao_governo_override", "componente_contrato_governo", componente.id, ator_id, {
        "contrato_id": contrato.id, "antes": antes, "depois": {"comissionavel": novo_comissionavel, "taxa": nova_taxa},
        "motivo": motivo, "aprovado_por": aprovado_por, "representante_id": contrato.representante_id, "origem": "governo"})
    db.commit()
    return componente


def transferir(db: Session, contrato_id: int, *, representante_id: int | None, divisao: list[dict] | None, motivo: str,
               aprovado_por: str, ator_id: str | None) -> ContratoGoverno:
    """Transferência de carteira, divisão ou renovação conduzida pela empresa (`representante_id=None`, sem divisão)."""
    _exigir_aprovacao(motivo, aprovado_por)
    contrato = db.get(ContratoGoverno, contrato_id)
    if contrato is None:
        raise NaoEncontrado(f"Contrato {contrato_id} não encontrado")
    for rid in [representante_id] * bool(representante_id) + [item["representante_id"] for item in divisao or []]:
        if db.get(Representante, rid) is None:
            raise NaoEncontrado(f"Representante {rid} não encontrado")
    if divisao and sum(Decimal(str(item["fracao"])) for item in divisao) != 1:
        raise ValidacaoFalhou("A divisão de comissão precisa somar 1 (100%).")
    antes = {"representante_id": contrato.representante_id, "divisao": contrato.divisao_comissao}
    contrato.representante_id, contrato.divisao_comissao = representante_id, divisao
    auditoria_service.registrar(db, contrato.tenant_id, "comissao_governo_transferida", "contrato_governo", contrato.id, ator_id, {
        "contrato_id": contrato.id, "antes": antes, "depois": {"representante_id": representante_id, "divisao": divisao},
        "motivo": motivo, "aprovado_por": aprovado_por, "origem": "governo"})
    db.commit()
    return contrato


def listar(db: Session, contrato_id: int | None = None, representante_id: int | None = None) -> list[dict]:
    consulta = db.query(ComissaoRepresentante).filter(ComissaoRepresentante.contrato_governo_id.isnot(None))
    if contrato_id:
        consulta = consulta.filter_by(contrato_governo_id=contrato_id)
    if representante_id:
        consulta = consulta.filter_by(representante_id=representante_id)
    return [{"id": c.id, "representante_id": c.representante_id, "tenant_id": c.tenant_id, "contrato_id": c.contrato_governo_id,
             "componente_id": c.componente_governo_id, "componente_tipo": c.componente_tipo, "recebimento_id": c.recebimento_governo_id,
             "numero_renovacao": c.numero_renovacao, "apuracao_id": c.apuracao_id,
             "base_calculo": c.base_calculo, "taxa": c.taxa, "fracao": c.fracao_divisao,
             "evento": c.evento, "valor": c.valor_comissao, "status": c.status,
             "criado_em": c.criado_em.isoformat() if c.criado_em else None, "pago_em": c.pago_em.isoformat() if c.pago_em else None}
            for c in consulta.order_by(ComissaoRepresentante.id).all()]
