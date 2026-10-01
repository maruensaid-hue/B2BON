"""Contratos Government (D-072): contratação inicial, períodos anuais, renovação, componentes e pool anual
de AI Credits.

- Ano 1: Licença + Implantação + Subscrição anual inicial (modelo A) ou só subscrição (modelo B, licença 0).
- Ano 2+: Subscrição anual de renovação (+ serviços e créditos adicionais quando contratados). A licença
  nunca é cobrada de novo numa renovação.
- O pool anual de AI Credits é um lote da carteira universal (mesmo ledger, mesmo FEFO, mesmo AI Gateway):
  vence no fim do período e um período novo concede um pool novo.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.finops import contract as finops
from app.contexts.governo import comissoes, ofertas, politicas
from app.contexts.governo.tipos import ADICIONAIS, RECORRENTES, Componente, Gatilho, ModeloCobranca
from app.core.config import settings
from app.models.carteira_creditos import MovimentoCredito
from app.models.contrato_governo import ComponenteContratoGoverno, ContratoGoverno, PeriodoAssinaturaGoverno, RecebimentoGoverno
from app.models.creditos_ia import LoteCreditos
from app.models.licenca import Licenca
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada, ValidacaoFalhou

ZERO = Decimal(0)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


def hoje() -> date:
    return datetime.now(UTC).date()


def mais_um_ano(dia: date) -> date:
    try:
        return dia.replace(year=dia.year + 1)
    except ValueError:  # 29/02
        return dia.replace(year=dia.year + 1, day=28)


def _auditar(db: Session, contrato: ContratoGoverno, evento: str, entidade: str, entidade_id: int, ator_id: str | None, detalhes: dict):
    auditoria_service.registrar(db, contrato.tenant_id, evento, entidade, entidade_id, ator_id,
                                {"contrato_id": contrato.id, "origem": "governo", **detalhes})


def obter(db: Session, contrato_id: int, tenant_id: str | None = None) -> ContratoGoverno:
    """`tenant_id` informado = visão do cliente: contrato de outro tenant é 404."""
    consulta = db.query(ContratoGoverno).filter_by(id=contrato_id)
    if tenant_id is not None:
        consulta = consulta.filter_by(tenant_id=tenant_id)
    contrato = consulta.one_or_none()
    if contrato is None:
        raise NaoEncontrado(f"Contrato {contrato_id} não encontrado")
    return contrato


def periodos(db: Session, contrato: ContratoGoverno) -> list[PeriodoAssinaturaGoverno]:
    return db.query(PeriodoAssinaturaGoverno).filter_by(contrato_id=contrato.id).order_by(PeriodoAssinaturaGoverno.numero).all()


def componentes(db: Session, contrato: ContratoGoverno) -> list[ComponenteContratoGoverno]:
    return db.query(ComponenteContratoGoverno).filter_by(contrato_id=contrato.id).order_by(ComponenteContratoGoverno.id).all()


def _regra_componente(contrato: ContratoGoverno, tipo: Componente) -> dict:
    return (contrato.politica_comissao.get("componentes") or {}).get(tipo.value) or {"comissionavel": False, "taxa": None}


def _componente(db: Session, contrato: ContratoGoverno, tipo: Componente, valor: Decimal, booking_em: date,
                periodo: PeriodoAssinaturaGoverno | None = None, descricao: str | None = None) -> ComponenteContratoGoverno:
    regra = _regra_componente(contrato, tipo)
    componente = ComponenteContratoGoverno(
        contrato_id=contrato.id, periodo_id=periodo.id if periodo else None, tenant_id=contrato.tenant_id, tipo=tipo.value,
        descricao=descricao, valor=valor, recorrente=tipo in RECORRENTES, comissionavel=bool(regra.get("comissionavel")),
        taxa_comissao=regra.get("taxa"), booking_em=booking_em, cancelado=False,
    )
    db.add(componente)
    db.flush()
    if contrato.politica_comissao.get("gatilho") == Gatilho.CONTRATO_ASSINADO.value:
        comissoes.reconhecer_na_contratacao(db, contrato, componente)
    return componente


def _ativar_licenca(db: Session, contrato: ContratoGoverno, ator_id: str | None) -> None:
    """O tenant passa a usar o plano Government. Sem vencimento automático nem cobrança mensal: o contrato manda."""
    licenca = db.query(Licenca).filter_by(tenant_id=contrato.tenant_id).one_or_none()
    antes = {"plano_id": licenca.plano_id, "status": licenca.status} if licenca else None
    if licenca is None:
        licenca = Licenca(tenant_id=contrato.tenant_id, plano_id=contrato.plano_id, status="ativa")
        db.add(licenca)
    licenca.plano_id, licenca.status, licenca.data_expiracao = contrato.plano_id, "ativa", None
    db.flush()
    _auditar(db, contrato, "licenca_governo_ativada", "licenca", licenca.id, ator_id,
             {"antes": antes, "depois": {"plano_id": contrato.plano_id, "status": "ativa"}})


def _validar_representantes(db: Session, representante_id: int | None, divisao: list[dict] | None) -> None:
    ids = [representante_id] if representante_id else []
    ids += [item["representante_id"] for item in divisao or []]
    for rid in ids:
        if db.get(Representante, rid) is None:
            raise NaoEncontrado(f"Representante {rid} não encontrado")
    if divisao:
        total = sum(Decimal(str(item["fracao"])) for item in divisao)
        if any(Decimal(str(item["fracao"])) <= 0 for item in divisao) or total != 1:
            raise ValidacaoFalhou("A divisão de comissão precisa somar 1 (100%), com frações positivas.")


def conceder_pool(db: Session, contrato: ContratoGoverno, periodo: PeriodoAssinaturaGoverno, ator_id: str | None = None) -> None:
    """Pool anual do período na carteira universal; idempotente por período."""
    if periodo.lote_creditos_id is not None or not contrato.creditos_ia_anuais:
        return
    lote = finops.carteira.conceder(
        db, contrato.tenant_id, finops.comercial.TipoLote.SUBSCRIPTION, contrato.creditos_ia_anuais, "POOL_ANUAL_GOVERNO",
        referencia=f"contrato_governo:{contrato.id}:periodo:{periodo.numero}", expira_em=datetime.combine(periodo.fim, datetime.min.time()),
        receita_por_credito=finops.comercial.receita_por_credito_assinatura(), idempotency_key=f"governo:periodo:{periodo.id}",
        ator_id=ator_id, descricao=f"AI Credits anuais — {contrato.referencia_contrato} período {periodo.numero}",
    )
    periodo.lote_creditos_id = lote.id
    db.flush()


def criar(db: Session, *, tenant_id: str, plano_id: int, modelo: str, referencia_contrato: str, entidade_governamental: str,
          assinado_em: date, inicio: date | None = None, representante_id: int | None = None, divisao_comissao: list[dict] | None = None,
          oportunidade_id: int | None = None, valores: dict | None = None, motivo_valores: str | None = None,
          regra_reajuste: dict | None = None, ator_id: str | None = None) -> ContratoGoverno:
    if db.get(Tenant, tenant_id) is None:
        raise NaoEncontrado(f"Tenant {tenant_id} não encontrado")
    plano = ofertas.obter_plano(db, plano_id)
    try:
        modelo_enum = ModeloCobranca(modelo)
    except ValueError as erro:
        raise ValidacaoFalhou(f"Modelo de cobrança inválido: {modelo}") from erro
    if modelo_enum not in (ModeloCobranca.LICENCA_MAIS_ASSINATURA, ModeloCobranca.SO_ASSINATURA):
        raise ValidacaoFalhou("Contrato governamental usa um dos modelos Government.")
    _validar_representantes(db, representante_id, divisao_comissao)
    catalogo = ofertas.oferta(plano)
    valores = dict(valores or {})
    if modelo_enum == ModeloCobranca.SO_ASSINATURA:
        # Subscription Only: sem licença; implantação, subscrição e pool vêm da contratação (sem preço público)
        faltando = [c for c in ("implantacao", "assinatura_anual", "creditos_ia_anuais") if valores.get(c) is None]
        if faltando:
            raise ValidacaoFalhou(f"Subscription Only: informe {', '.join(faltando)}.")
        valores["licenca"] = 0
    final = {chave: valores.get(chave, catalogo[chave]) for chave in ("licenca", "implantacao", "assinatura_anual", "creditos_ia_anuais")}
    negociado = modelo_enum == ModeloCobranca.LICENCA_MAIS_ASSINATURA and (
        any(_d(final[c]) != _d(catalogo[c]) for c in ("licenca", "implantacao", "assinatura_anual"))
        or final["creditos_ia_anuais"] != catalogo["creditos_ia_anuais"])
    if negociado and not (motivo_valores or "").strip():
        raise ValidacaoFalhou("Valores diferentes do catálogo (desconto/condição do edital) exigem motivo.")
    if any(_d(final[c]) < 0 for c in ("licenca", "implantacao", "assinatura_anual")) or _d(final["assinatura_anual"]) <= 0:
        raise ValidacaoFalhou("Valores inválidos: a subscrição anual precisa ser positiva e nenhum componente pode ser negativo.")

    politica = politicas.politica_vigente(db)
    contrato = ContratoGoverno(
        tenant_id=tenant_id, plano_id=plano.id, oportunidade_id=oportunidade_id, modelo_cobranca=modelo_enum.value,
        referencia_contrato=referencia_contrato, entidade_governamental=entidade_governamental, status="ATIVO", assinado_em=assinado_em,
        valor_licenca=_d(final["licenca"]), valor_implantacao=_d(final["implantacao"]), valor_assinatura_anual=_d(final["assinatura_anual"]),
        creditos_ia_anuais=int(final["creditos_ia_anuais"] or 0), regra_reajuste=regra_reajuste, politica_comissao=politica.regras,
        politica_comissao_versao=politica.versao, representante_id=representante_id, divisao_comissao=divisao_comissao, criado_por=ator_id,
    )
    db.add(contrato)
    db.flush()
    inicio = inicio or assinado_em
    periodo = PeriodoAssinaturaGoverno(contrato_id=contrato.id, tenant_id=tenant_id, numero=1, inicio=inicio, fim=mais_um_ano(inicio),
                                       valor_assinatura=contrato.valor_assinatura_anual, valor_reajuste=ZERO, status="ATIVO",
                                       status_renovacao="NAO_INICIADA")
    db.add(periodo)
    db.flush()
    if contrato.valor_licenca > 0:
        _componente(db, contrato, Componente.LICENCA, contrato.valor_licenca, assinado_em, descricao="Licença institucional")
    if contrato.valor_implantacao > 0:
        _componente(db, contrato, Componente.IMPLANTACAO, contrato.valor_implantacao, assinado_em, descricao="Implantação")
    _componente(db, contrato, Componente.ASSINATURA_INICIAL, contrato.valor_assinatura_anual, assinado_em, periodo, "Subscrição anual inicial")
    _ativar_licenca(db, contrato, ator_id)
    if periodo.inicio <= hoje():
        conceder_pool(db, contrato, periodo, ator_id)
    _auditar(db, contrato, "contrato_governo_criado", "contrato_governo", contrato.id, ator_id, {
        "plano": plano.nome, "modelo": contrato.modelo_cobranca, "valores": {k: float(_d(v)) for k, v in final.items()},
        "catalogo": {k: catalogo[k] for k in ("licenca", "implantacao", "assinatura_anual", "creditos_ia_anuais")},
        "negociado": bool(negociado), "motivo": motivo_valores, "politica_comissao_versao": politica.versao,
        "representante_id": representante_id, "divisao_comissao": divisao_comissao,
    })
    db.commit()
    return contrato


def renovar(db: Session, contrato_id: int, *, valor_assinatura=None, motivo_reajuste: str | None = None,
            ator_id: str | None = None) -> PeriodoAssinaturaGoverno:
    """Novo período anual: só a subscrição (com o reajuste contratual informado). Nunca a licença."""
    contrato = obter(db, contrato_id)
    if contrato.status != "ATIVO":
        raise RegraNegocioViolada("Só contrato ativo é renovado.")
    ultimo = periodos(db, contrato)[-1]
    if ultimo.status_renovacao == "RENOVADA":
        raise RegraNegocioViolada("Este período já foi renovado.")
    valor = _d(valor_assinatura) if valor_assinatura is not None else _d(ultimo.valor_assinatura)
    reajuste = valor - _d(ultimo.valor_assinatura)
    if valor <= 0:
        raise ValidacaoFalhou("Valor de renovação precisa ser positivo.")
    if reajuste != 0 and not (motivo_reajuste or "").strip():
        raise ValidacaoFalhou("Reajuste exige o motivo (regra contratual aplicada).")
    novo = PeriodoAssinaturaGoverno(contrato_id=contrato.id, tenant_id=contrato.tenant_id, numero=ultimo.numero + 1, inicio=ultimo.fim,
                                    fim=mais_um_ano(ultimo.fim), valor_assinatura=valor, valor_reajuste=reajuste, status="ATIVO",
                                    status_renovacao="NAO_INICIADA")
    db.add(novo)
    db.flush()
    ultimo.status_renovacao = "RENOVADA"
    _componente(db, contrato, Componente.RENOVACAO, valor, hoje(), novo, f"Renovação #{novo.numero - 1} da subscrição anual")
    if novo.inicio <= hoje():
        conceder_pool(db, contrato, novo, ator_id)
    _auditar(db, contrato, "contrato_governo_renovado", "periodo_assinatura_governo", novo.id, ator_id, {
        "numero_renovacao": novo.numero - 1, "antes": float(ultimo.valor_assinatura), "depois": float(valor), "reajuste": float(reajuste),
        "regra_reajuste": contrato.regra_reajuste, "motivo": motivo_reajuste,
    })
    db.commit()
    return novo


def adicionar_componente(db: Session, contrato_id: int, *, tipo: str, valor, descricao: str | None = None, creditos: int | None = None,
                         ator_id: str | None = None) -> ComponenteContratoGoverno:
    """Serviços adicionais ou AI Credits adicionais contratados (os créditos entram como pacote na mesma carteira)."""
    contrato = obter(db, contrato_id)
    tipo_enum = Componente(tipo)
    if tipo_enum not in ADICIONAIS:
        raise ValidacaoFalhou("Só serviços adicionais ou AI Credits adicionais podem ser acrescentados.")
    valor = _d(valor)
    if valor <= 0:
        raise ValidacaoFalhou("Valor do componente precisa ser positivo.")
    atual = periodo_vigente(db, contrato)
    componente = _componente(db, contrato, tipo_enum, valor, hoje(), atual, descricao)
    if tipo_enum == Componente.CREDITOS:
        if not creditos or creditos <= 0:
            raise ValidacaoFalhou("Informe a quantidade de AI Credits adicionais.")
        finops.carteira.conceder(
            db, contrato.tenant_id, finops.comercial.TipoLote.TOPUP, creditos, "CREDITOS_ADICIONAIS_GOVERNO",
            referencia=f"componente_governo:{componente.id}",
            expira_em=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30 * finops.comercial.validade_topup_meses()),
            receita_por_credito=valor / Decimal(creditos), idempotency_key=f"governo:componente:{componente.id}", ator_id=ator_id,
            descricao=descricao or "AI Credits adicionais (contrato governamental)",
        )
    _auditar(db, contrato, "componente_governo_adicionado", "componente_contrato_governo", componente.id, ator_id,
             {"tipo": tipo_enum.value, "valor": float(valor), "creditos": creditos})
    db.commit()
    return componente


def cancelar(db: Session, contrato_id: int, motivo: str, ator_id: str | None = None) -> ContratoGoverno:
    """Cancela o contrato: sai do ARR; componentes sem recebimento saem dos bookings; recebimentos ficam."""
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo do cancelamento.")
    contrato = obter(db, contrato_id)
    contrato.status = "CANCELADO"
    for periodo in periodos(db, contrato):
        if periodo.status == "ATIVO":
            periodo.status = "CANCELADO"
    recebidos = {c for (c,) in db.query(RecebimentoGoverno.componente_id).filter_by(contrato_id=contrato.id, estornado_em=None)}
    for componente in componentes(db, contrato):
        if componente.id not in recebidos:
            componente.cancelado = True
    _auditar(db, contrato, "contrato_governo_cancelado", "contrato_governo", contrato.id, ator_id, {"motivo": motivo})
    db.commit()
    return contrato


def periodo_vigente(db: Session, contrato: ContratoGoverno, dia: date | None = None) -> PeriodoAssinaturaGoverno | None:
    dia = dia or hoje()
    return (db.query(PeriodoAssinaturaGoverno).filter(
        PeriodoAssinaturaGoverno.contrato_id == contrato.id, PeriodoAssinaturaGoverno.status == "ATIVO",
        PeriodoAssinaturaGoverno.inicio <= dia, PeriodoAssinaturaGoverno.fim > dia).one_or_none())


def rotina(db: Session, dia: date | None = None) -> dict:
    """De hora em hora (cron de AI Credits): concede o pool do período que começou, encerra o que terminou
    e marca a notificação de renovação dentro da janela configurada."""
    dia = dia or hoje()
    concedidos = encerrados = notificados = 0
    janela = timedelta(days=settings.governo_aviso_renovacao_dias)
    for periodo in db.query(PeriodoAssinaturaGoverno).filter_by(status="ATIVO").all():
        contrato = db.get(ContratoGoverno, periodo.contrato_id)
        if periodo.fim <= dia:
            periodo.status = "ENCERRADO"
            encerrados += 1
            continue
        if periodo.inicio <= dia and periodo.lote_creditos_id is None and contrato.creditos_ia_anuais:
            conceder_pool(db, contrato, periodo)
            concedidos += 1
        if periodo.status_renovacao == "NAO_INICIADA" and periodo.fim - janela <= dia:
            periodo.status_renovacao = "NOTIFICADA"
            periodo.notificacao_renovacao_em = datetime.now(UTC).replace(tzinfo=None)
            _auditar(db, contrato, "renovacao_governo_notificada", "periodo_assinatura_governo", periodo.id, None,
                     {"data_renovacao": periodo.fim.isoformat(), "valor": float(periodo.valor_assinatura)})
            notificados += 1
    db.commit()
    return {"pools_concedidos": concedidos, "periodos_encerrados": encerrados, "renovacoes_notificadas": notificados}


def pool(db: Session, periodo: PeriodoAssinaturaGoverno) -> dict | None:
    """annual_credit_pool, credits_consumed, credits_remaining, valid_from, valid_until, credit_source, subscription_id, tenant_id."""
    if periodo.lote_creditos_id is None:
        return None
    lote = db.get(LoteCreditos, periodo.lote_creditos_id)
    consumido = -Decimal(str(db.query(func.sum(MovimentoCredito.quantidade)).filter(
        MovimentoCredito.lote_id == lote.id, MovimentoCredito.tipo.in_(("CREDIT_CONSUMED", "CREDIT_REFUNDED"))).scalar() or 0))
    return {"annual_credit_pool": float(lote.quantidade_original), "credits_consumed": float(consumido),
            "credits_remaining": float(lote.quantidade_restante), "valid_from": lote.concedido_em.isoformat(),
            "valid_until": lote.expira_em.isoformat() if lote.expira_em else None, "credit_source": lote.origem, "status": lote.status,
            "subscription_id": periodo.id, "tenant_id": periodo.tenant_id}


def _periodo_dict(db: Session, periodo: PeriodoAssinaturaGoverno) -> dict:
    return {"id": periodo.id, "numero": periodo.numero, "renovacao_numero": periodo.numero - 1, "inicio": periodo.inicio.isoformat(),
            "fim": periodo.fim.isoformat(), "data_renovacao": periodo.fim.isoformat(), "valor_assinatura": float(periodo.valor_assinatura),
            "valor_reajuste": float(periodo.valor_reajuste), "status": periodo.status, "status_renovacao": periodo.status_renovacao,
            "notificacao_renovacao_em": periodo.notificacao_renovacao_em.isoformat() if periodo.notificacao_renovacao_em else None,
            "creditos": pool(db, periodo)}


def resumo(db: Session, contrato: ContratoGoverno, com_comissoes: bool = False) -> dict:
    """Visão do contrato. Para o cliente (`com_comissoes=False`) não sai representante nem comissão."""
    itens = componentes(db, contrato)
    recebido = {cid: Decimal(str(v or 0)) for cid, v in db.query(RecebimentoGoverno.componente_id, func.sum(RecebimentoGoverno.valor))
                .filter_by(contrato_id=contrato.id, estornado_em=None).group_by(RecebimentoGoverno.componente_id)}
    dados = {
        "id": contrato.id, "tenant_id": contrato.tenant_id, "plano_id": contrato.plano_id, "modelo_cobranca": contrato.modelo_cobranca,
        "referencia_contrato": contrato.referencia_contrato, "entidade_governamental": contrato.entidade_governamental,
        "status": contrato.status, "assinado_em": contrato.assinado_em.isoformat(),
        "valores": {"licenca": float(contrato.valor_licenca), "implantacao": float(contrato.valor_implantacao),
                    "assinatura_anual": float(contrato.valor_assinatura_anual),
                    "contratacao_inicial": float(ofertas.contratacao_inicial(contrato.valor_licenca, contrato.valor_implantacao,
                                                                             contrato.valor_assinatura_anual)),
                    "creditos_ia_anuais": contrato.creditos_ia_anuais},
        "regra_reajuste": contrato.regra_reajuste,
        "periodos": [_periodo_dict(db, p) for p in periodos(db, contrato)],
        "componentes": [{"id": c.id, "tipo": c.tipo, "descricao": c.descricao, "valor": float(c.valor), "recorrente": c.recorrente,
                         "booking_em": c.booking_em.isoformat(), "cancelado": c.cancelado, "recebido": float(recebido.get(c.id, ZERO)),
                         **({"comissionavel": c.comissionavel, "taxa_comissao": c.taxa_comissao} if com_comissoes else {})}
                        for c in itens],
    }
    if com_comissoes:
        dados.update({"representante_id": contrato.representante_id, "divisao_comissao": contrato.divisao_comissao,
                      "politica_comissao": contrato.politica_comissao, "politica_comissao_versao": contrato.politica_comissao_versao})
    return dados


def do_tenant(db: Session, tenant_id: str) -> dict | None:
    """Contrato ativo mais recente do tenant (área do cliente)."""
    contrato = (db.query(ContratoGoverno).filter_by(tenant_id=tenant_id, status="ATIVO")
                .order_by(ContratoGoverno.assinado_em.desc(), ContratoGoverno.id.desc()).first())
    return resumo(db, contrato) if contrato else None
