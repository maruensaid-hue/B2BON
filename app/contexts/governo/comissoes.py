"""Comissão Government (D-072), componente por componente, sobre o motor de comissões existente
(`comissao_representante` + repasse mensal por Pix já usado nos planos privados).

- Taxa e "comissionável" vêm do componente (cópia da política do contrato); nunca de um total.
- D-073: a base é o lucro líquido do recebimento (bruto − impostos − infraestrutura, `comissao_service`).
- Gatilho PAYMENT_RECEIVED: cada recebimento gera a comissão daquele valor (parcelas = proporcional).
  CONTRACT_SIGNED: o componente inteiro na contratação.
- Estorno de recebimento: comissão ainda não repassada é anulada; já repassada vira um CLAWBACK
  negativo "a_compensar".
- Dono da comissão: o representante do contrato (ou a divisão configurada). Transferir a carteira muda só
  o futuro; comissões já geradas ficam com quem as gerou.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.governo.tipos import Componente, Gatilho
from app.models.comissao_representante import ComissaoRepresentante
from app.models.contrato_governo import ComponenteContratoGoverno, ContratoGoverno, PeriodoAssinaturaGoverno, RecebimentoGoverno
from app.models.representante import Representante
from app.services import auditoria_service, comissao_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou



def _beneficiarios(contrato: ContratoGoverno) -> list[tuple[int, Decimal]]:
    if contrato.divisao_comissao:
        return [(int(item["representante_id"]), Decimal(str(item["fracao"]))) for item in contrato.divisao_comissao]
    return [(contrato.representante_id, Decimal(1))] if contrato.representante_id else []


def _numero_renovacao(db: Session, componente: ComponenteContratoGoverno) -> int | None:
    if componente.tipo != Componente.RENOVACAO.value or componente.periodo_id is None:
        return None
    return db.get(PeriodoAssinaturaGoverno, componente.periodo_id).numero - 1


def _gerar(db: Session, contrato: ContratoGoverno, componente: ComponenteContratoGoverno, base: Decimal,
           recebimento: RecebimentoGoverno | None) -> list[ComissaoRepresentante]:
    if not componente.comissionavel or not componente.taxa_comissao or componente.cancelado:
        return []
    taxa = Decimal(str(componente.taxa_comissao))
    geradas = []
    for representante_id, fracao in _beneficiarios(contrato):
        existente = db.query(ComissaoRepresentante).filter_by(
            representante_id=representante_id, componente_governo_id=componente.id, evento="ACCRUAL",
            recebimento_governo_id=recebimento.id if recebimento else None).first()
        if existente is not None:  # idempotente
            continue
        comissao = ComissaoRepresentante(
            representante_id=representante_id, tenant_id=contrato.tenant_id, recebimento_governo_id=recebimento.id if recebimento else None,
            componente_governo_id=componente.id, contrato_governo_id=contrato.id, componente_tipo=componente.tipo,
            numero_renovacao=_numero_renovacao(db, componente), evento="ACCRUAL",
        )
        comissao_service.calcular(db, comissao, base, taxa, fracao)  # D-073: sobre o lucro líquido
        db.add(comissao)
        geradas.append(comissao)
    db.flush()
    return geradas


def reconhecer_na_contratacao(db: Session, contrato: ContratoGoverno, componente: ComponenteContratoGoverno) -> list[ComissaoRepresentante]:
    return _gerar(db, contrato, componente, Decimal(str(componente.valor)), None)


def reconhecer_recebimento(db: Session, contrato: ContratoGoverno, componente: ComponenteContratoGoverno,
                           recebimento: RecebimentoGoverno) -> list[ComissaoRepresentante]:
    if contrato.politica_comissao.get("gatilho") != Gatilho.PAGAMENTO_RECEBIDO.value:
        return []
    return _gerar(db, contrato, componente, Decimal(str(recebimento.valor)), recebimento)


def estornar_recebimento(db: Session, recebimento: RecebimentoGoverno) -> dict:
    anuladas = compensar = 0
    for comissao in db.query(ComissaoRepresentante).filter_by(recebimento_governo_id=recebimento.id, evento="ACCRUAL").all():
        if comissao.status in ("calculada", comissao_service.PENDENTE):
            comissao.status = "estornada"
            anuladas += 1
        elif comissao.status == "paga":
            db.add(ComissaoRepresentante(
                representante_id=comissao.representante_id, tenant_id=comissao.tenant_id, recebimento_governo_id=recebimento.id,
                componente_governo_id=comissao.componente_governo_id, contrato_governo_id=comissao.contrato_governo_id,
                componente_tipo=comissao.componente_tipo, base_calculo=-(comissao.base_calculo or 0),
                base_bruta=-(comissao.base_bruta or 0), deducoes=comissao.deducoes, taxa=comissao.taxa,
                fracao_divisao=comissao.fracao_divisao, numero_renovacao=comissao.numero_renovacao, evento="CLAWBACK",
                valor_comissao=-comissao.valor_comissao, status="a_compensar",
            ))
            compensar += 1
    db.flush()
    return {"anuladas": anuladas, "a_compensar": compensar}


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
             "numero_renovacao": c.numero_renovacao, "base_bruta": c.base_bruta, "deducoes": c.deducoes,
             "base_calculo": c.base_calculo, "taxa": c.taxa, "fracao": c.fracao_divisao,
             "evento": c.evento, "valor": c.valor_comissao, "status": c.status,
             "criado_em": c.criado_em.isoformat() if c.criado_em else None, "pago_em": c.pago_em.isoformat() if c.pago_em else None}
            for c in consulta.order_by(ComissaoRepresentante.id).all()]
