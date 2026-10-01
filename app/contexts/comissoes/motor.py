"""Commission Engine único (D-074). Nenhum módulo de vendas calcula comissão: eles registram o recebimento aqui.

    PAYMENT RECEIVED → classificação da receita → Tax Profile → Infrastructure Cost Model
    → Margem Comissionável Líquida → política (taxa) → CALCULATED → ACCRUED → PAYABLE → PAID

Margem Comissionável Líquida = receita recebida − impostos atribuíveis − custo de infraestrutura atribuível (D-076: o
custo PROVISIONADO do Infrastructure Cost Pool; o real fica ao lado, para FinOps e MAP). Não é o
"lucro líquido da empresa": despesas corporativas não atribuídas à venda não entram.

Duas condições para PAYABLE: (A) parâmetros de custo disponíveis e (B) receita recebida. Como a apuração nasce do
recebimento, (B) já vale; sem (A) a comissão fica AWAITING_COST_PARAMETERS (valor 0, com o parâmetro faltante) e é
recalculada sozinha quando o PO informar. Comissão calculada guarda o snapshot e só muda por recálculo explícito e
auditado; comissão PAID nunca muda.
"""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.contexts.comissoes import infraestrutura, politica, tributos
from app.contexts.comissoes.tipos import RECEITA_SAAS, STATUS_VALOR, Faltante, Origem, Status
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.comissao_representante import ComissaoRepresentante
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

CENTAVO = Decimal("0.01")
NAO_RECALCULAVEIS = (Status.PAGA, Status.ESTORNADA, Status.COMPENSAR)
# D-077: mudança de preço/parâmetro nunca recalcula comissão já fixada (PAYABLE ou PAID); só o que ainda não tem valor final.
FIXADAS = (Status.PAGAVEL, *NAO_RECALCULAVEIS)


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def apurar(db: Session, apuracao: ApuracaoComissao) -> ApuracaoComissao:
    """Receita bruta → impostos (Tax Engine, perfil vigente na data) → infraestrutura (Infrastructure Cost Pool: provisionado
    para a comissão, real em separado) → custo de IA (sempre medido; deduzido só se a política da margem mandar) → margem."""
    bruto = _d(apuracao.receita_bruta)
    faltantes, detalhe = [], {}
    perfil = tributos.aplicavel(db, apuracao.tipo_receita, apuracao.recebido_em)
    apuracao.perfil_tributario_id = perfil.id if perfil else None
    apuracao.impostos = apuracao.aliquota_tributaria = None
    if perfil is not None:
        apuracao.impostos, detalhe["tributos"] = tributos.calcular(db, perfil, apuracao)
        if apuracao.impostos is not None and bruto:
            apuracao.aliquota_tributaria = float((apuracao.impostos / bruto).quantize(Decimal("0.000001")))
    else:
        detalhe["tributos"] = {"pendencias": [f"Tax Profile para {apuracao.tipo_receita}"]}
    if apuracao.impostos is None:
        faltantes.append(Faltante.PERFIL_TRIBUTARIO.value)
    regras_margem, regras_infra = politica.vigente(db), politica.vigente_infra(db)
    detalhe["politica_margem"] = {"versao": regras_margem.versao, **regras_margem.regras}
    detalhe["politica_infra_versao"] = regras_infra.versao
    apuracao.custo_infra, apuracao.custo_infra_real, detalhe["infraestrutura"] = infraestrutura.alocar(db, apuracao)
    usa_real = regras_infra.regras.get("custo_comissao") == "ACTUAL"
    custo_comissao = apuracao.custo_infra_real if usa_real else apuracao.custo_infra
    if custo_comissao is None:
        faltantes.append(detalhe["infraestrutura"].get("faltante") or Faltante.CUSTO_INFRA.value)
    custo_ia, motivo_ia = infraestrutura.custo_ia(db, apuracao)
    deduz_ia = bool(regras_margem.regras.get("deduzir_custo_ia"))
    if deduz_ia and custo_ia is None:
        faltantes.append(motivo_ia or Faltante.CAMBIO.value)
    apuracao.parametros_faltantes = sorted(set(faltantes), key=faltantes.index) or None
    apuracao.detalhe = detalhe
    if faltantes:
        apuracao.status, apuracao.margem_comissionavel_liquida, apuracao.calculado_em = Status.AGUARDANDO.value, None, None
    else:
        margem = bruto - apuracao.impostos - custo_comissao - (custo_ia if deduz_ia else 0)
        apuracao.margem_comissionavel_liquida = margem.quantize(CENTAVO, ROUND_HALF_UP)
        apuracao.status, apuracao.calculado_em = Status.CALCULADA.value, _agora()
    db.flush()
    return apuracao


def _avancar(comissao: ComissaoRepresentante, apuracao: ApuracaoComissao) -> None:
    """Valor = margem × taxa × fração; com a margem conhecida e a receita recebida: CALCULATED → ACCRUED → PAYABLE."""
    if apuracao.status != Status.CALCULADA.value:
        comissao.base_calculo, comissao.valor_comissao, comissao.status = None, 0.0, Status.AGUARDANDO.value
        return
    base = (_d(apuracao.margem_comissionavel_liquida) * _d(comissao.fracao_divisao or 1)).quantize(CENTAVO, ROUND_HALF_UP)
    agora = _agora()
    comissao.base_calculo = float(base)
    comissao.valor_comissao = float((base * _d(comissao.taxa)).quantize(CENTAVO, ROUND_HALF_UP))
    comissao.calculado_em = comissao.provisionado_em = comissao.pagavel_em = agora
    comissao.status = Status.PAGAVEL.value


def registrar_recebimento(db: Session, *, origem: Origem, tenant_id: str, segmento: str, produto: str, tipo_receita: str,
                          recebido_em: date, receita_bruta, beneficiarios: list[tuple[int, Decimal]], taxa: float | None,
                          pagamento_licenca_id: int | None = None, recebimento_governo_id: int | None = None,
                          componente_tipo: str | None = None, meta: dict | None = None, meses_infra: float = 0.0) -> tuple[ApuracaoComissao, list[ComissaoRepresentante]]:
    """Ponto único de entrada: apura o recebimento e gera a comissão de cada beneficiário (se houver taxa)."""
    chave = {"pagamento_licenca_id": pagamento_licenca_id} if pagamento_licenca_id else {"recebimento_governo_id": recebimento_governo_id}
    apuracao = db.query(ApuracaoComissao).filter_by(**chave).one_or_none()
    if apuracao is None:
        apuracao = ApuracaoComissao(tenant_id=tenant_id, origem=origem.value, segmento=segmento, produto=produto, tipo_receita=tipo_receita,
                                    componente_tipo=componente_tipo, recebido_em=recebido_em, receita_bruta=_d(receita_bruta).quantize(CENTAVO),
                                    meses_infra=meses_infra, status=Status.AGUARDANDO.value, **chave)
        db.add(apuracao)
        db.flush()
        apurar(db, apuracao)
    geradas = []
    for representante_id, fracao in beneficiarios if taxa else []:
        if db.query(ComissaoRepresentante).filter_by(apuracao_id=apuracao.id, representante_id=representante_id, evento="ACCRUAL").first():
            continue  # idempotente
        comissao = ComissaoRepresentante(representante_id=representante_id, tenant_id=tenant_id, apuracao_id=apuracao.id,
                                         pagamento_licenca_id=pagamento_licenca_id, recebimento_governo_id=recebimento_governo_id,
                                         componente_tipo=componente_tipo, taxa=float(taxa), fracao_divisao=float(fracao), evento="ACCRUAL",
                                         valor_comissao=0.0, **(meta or {}))
        _avancar(comissao, apuracao)
        db.add(comissao)
        geradas.append(comissao)
    db.flush()
    return apuracao, geradas


def recalcular_aguardando(db: Session) -> int:
    """Depois de um Tax Profile ou Infrastructure Cost Model novo: apurações em espera são refeitas e, se completas,
    as comissões delas passam a PAYABLE. Calculadas e pagas não mudam."""
    contador = 0
    for apuracao in db.query(ApuracaoComissao).filter_by(status=Status.AGUARDANDO.value).order_by(ApuracaoComissao.recebido_em).all():
        apurar(db, apuracao)
        for comissao in db.query(ComissaoRepresentante).filter_by(apuracao_id=apuracao.id, status=Status.AGUARDANDO.value).all():
            _avancar(comissao, apuracao)
        contador += apuracao.status == Status.CALCULADA.value
    for legado in db.query(ComissaoRepresentante).filter(ComissaoRepresentante.status == Status.AGUARDANDO.value,
                                                         ComissaoRepresentante.apuracao_id.is_(None)).all():
        contador += _reconstruir_legado(db, legado)
    db.flush()
    return contador


def _reconstruir_legado(db: Session, comissao: ComissaoRepresentante) -> int:
    """Comissão anterior à D-074 (calculada sobre o bruto, não paga): ganha a apuração do pagamento de origem."""
    from app.models.pagamento_licenca import PagamentoLicenca
    from app.models.plano import Plano

    if comissao.pagamento_licenca_id is None:
        return 0
    pagamento = db.get(PagamentoLicenca, comissao.pagamento_licenca_id)
    plano = db.get(Plano, pagamento.plano_id) if pagamento else None
    if pagamento is None:
        return 0
    apuracao, _ = registrar_recebimento(
        db, origem=Origem.PAGAMENTO_LICENCA, tenant_id=comissao.tenant_id, segmento="PRIVATE", produto=plano.nome if plano else "—",
        tipo_receita=RECEITA_SAAS, recebido_em=(pagamento.confirmado_em or comissao.criado_em or _agora()).date(),
        receita_bruta=pagamento.valor, beneficiarios=[], taxa=None, pagamento_licenca_id=pagamento.id, meses_infra=1.0)
    comissao.apuracao_id = apuracao.id
    _avancar(comissao, apuracao)
    return int(apuracao.status == Status.CALCULADA.value)


def recalcular_nao_pagas(db: Session, motivo: str, ator_id: str | None) -> dict:
    """Recálculo explícito e auditado das apurações sem comissão fixada, com os parâmetros vigentes na data de cada
    recebimento. Comissões PAYABLE (valor final), PAID, estornadas ou a compensar nunca mudam (D-077)."""
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Recálculo exige motivo.")
    alteradas = []
    for apuracao in db.query(ApuracaoComissao).filter(ApuracaoComissao.status != Status.ESTORNADA.value).all():
        comissoes = db.query(ComissaoRepresentante).filter_by(apuracao_id=apuracao.id, evento="ACCRUAL").all()
        if any(c.status in FIXADAS for c in comissoes):
            continue
        antes = {"margem": str(apuracao.margem_comissionavel_liquida), "valores": [c.valor_comissao for c in comissoes]}
        apurar(db, apuracao)
        for comissao in comissoes:
            _avancar(comissao, apuracao)
        depois = {"margem": str(apuracao.margem_comissionavel_liquida), "valores": [c.valor_comissao for c in comissoes]}
        if antes != depois:
            alteradas.append({"apuracao_id": apuracao.id, "antes": antes, "depois": depois})
    contagem = recalcular_aguardando(db)
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "comissoes_recalculadas", "apuracao_comissao", 0, ator_id,
                                {"motivo": motivo, "alteradas": alteradas, "aguardando_calculadas": contagem, "origem": "admin"})
    db.commit()
    return {"alteradas": len(alteradas), "aguardando_calculadas": contagem}


def estornar(db: Session, *, pagamento_licenca_id: int | None = None, recebimento_governo_id: int | None = None) -> dict:
    """Receita devolvida: comissão não paga é anulada; a paga vira CLAWBACK negativo a compensar."""
    chave = {"pagamento_licenca_id": pagamento_licenca_id} if pagamento_licenca_id else {"recebimento_governo_id": recebimento_governo_id}
    apuracao = db.query(ApuracaoComissao).filter_by(**chave).one_or_none()
    anuladas = compensar = 0
    if apuracao is None:
        return {"anuladas": 0, "a_compensar": 0}
    apuracao.status = Status.ESTORNADA.value
    for comissao in db.query(ComissaoRepresentante).filter_by(apuracao_id=apuracao.id, evento="ACCRUAL").all():
        if comissao.status == Status.PAGA.value:
            db.add(ComissaoRepresentante(
                representante_id=comissao.representante_id, tenant_id=comissao.tenant_id, apuracao_id=apuracao.id,
                recebimento_governo_id=comissao.recebimento_governo_id, componente_governo_id=comissao.componente_governo_id,
                contrato_governo_id=comissao.contrato_governo_id, componente_tipo=comissao.componente_tipo,
                base_calculo=-(comissao.base_calculo or 0), taxa=comissao.taxa, fracao_divisao=comissao.fracao_divisao,
                numero_renovacao=comissao.numero_renovacao, evento="CLAWBACK", valor_comissao=-comissao.valor_comissao,
                status=Status.COMPENSAR.value))
            compensar += 1
        elif comissao.status not in NAO_RECALCULAVEIS:
            comissao.status = Status.ESTORNADA.value
            anuladas += 1
    db.flush()
    return {"anuladas": anuladas, "a_compensar": compensar}


def _snapshot_tributario(apuracao: ApuracaoComissao) -> dict:
    """Snapshot tributário da apuração (D-078): perfil, CBS/IBS (alíquota-teste, situação, caixa), compensação e total."""
    tributos_ = (apuracao.detalhe or {}).get("tributos") or {}
    reforma = tributos_.get("reforma") or {}
    return {"tax_profile_id": apuracao.perfil_tributario_id, "cbs_test_rate": reforma.get("cbs_test_rate"),
            "ibs_test_rate": reforma.get("ibs_test_rate"), "cbs_ibs_status": reforma.get("status"),
            "cbs_cash_tax": reforma.get("cbs_cash_tax"), "ibs_cash_tax": reforma.get("ibs_cash_tax"),
            "pis_cofins_offset": reforma.get("pis_cofins_offset"), "total_attributable_tax": tributos_.get("total_attributable_tax"),
            "calculated_at": apuracao.calculado_em.isoformat() if apuracao.calculado_em else None}


def status_valor(apuracao: ApuracaoComissao) -> str:
    """commission_amount_status: o status da apuração ou, aguardando, AWAITING_<parâmetro> (infraestrutura, depois Tax
    Profile, depois câmbio). A lista completa fica em `missing_parameters`."""
    faltantes = apuracao.parametros_faltantes or []
    if apuracao.status != Status.AGUARDANDO.value or not faltantes:
        return apuracao.status
    return next((rotulo for chave, rotulo in STATUS_VALOR.items() if chave in faltantes), Status.AGUARDANDO.value)


def apuracao_dict(apuracao: ApuracaoComissao) -> dict:
    valor = lambda v: float(v) if v is not None else None  # noqa: E731
    return {"id": apuracao.id, "tenant_id": apuracao.tenant_id, "origem": apuracao.origem, "segmento": apuracao.segmento,
            "produto": apuracao.produto, "tipo_receita": apuracao.tipo_receita, "componente_tipo": apuracao.componente_tipo,
            "recebido_em": apuracao.recebido_em.isoformat(), "gross_revenue": valor(apuracao.receita_bruta),
            "tax_profile_id": apuracao.perfil_tributario_id, "tax_rate": apuracao.aliquota_tributaria, "tax_amount": valor(apuracao.impostos),
            "provisioned_infrastructure_cost": valor(apuracao.custo_infra), "actual_infrastructure_cost": valor(apuracao.custo_infra_real),
            "infrastructure_months": apuracao.meses_infra, "infrastructure_detail": (apuracao.detalhe or {}).get("infraestrutura"),
            "ai_cost_amount": valor(apuracao.custo_ia), "net_commissionable_margin": valor(apuracao.margem_comissionavel_liquida),
            "status": apuracao.status, "missing_parameters": apuracao.parametros_faltantes or [],
            "commission_amount_status": status_valor(apuracao), "tax_detail": (apuracao.detalhe or {}).get("tributos"),
            "tax_snapshot": _snapshot_tributario(apuracao),
            "calculated_at": apuracao.calculado_em.isoformat() if apuracao.calculado_em else None}
