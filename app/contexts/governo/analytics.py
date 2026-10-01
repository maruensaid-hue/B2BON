"""Métricas Government (D-072). Cada número vem de uma fonte só e nenhum se confunde com outro:

- Bookings: componentes contratados (por data de booking), separados em licença, serviços, subscrição e créditos.
- ARR: só subscrição anual elegível (períodos vigentes); licença e implantação nunca entram.
- New ARR: subscrição inicial contratada; Renewal ARR: subscrição de renovação contratada.
- TCV inicial: licença + implantação + subscrição inicial de cada contrato.
- Cash-In: recebimentos não estornados. Comissão: o que o motor de comissões gerou.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.finops import contract as finops
from app.contexts.governo import contratos as contratos_mod
from app.contexts.governo import pipeline
from app.contexts.governo.tipos import Componente
from app.models.comissao_representante import ComissaoRepresentante
from app.models.contrato_governo import ComponenteContratoGoverno, ContratoGoverno, PeriodoAssinaturaGoverno, RecebimentoGoverno
from app.models.plano import Plano
from app.services import comissao_service

ZERO = Decimal(0)
GRUPO_BOOKING = {
    Componente.LICENCA.value: "licenca", Componente.IMPLANTACAO.value: "servicos", Componente.SERVICOS.value: "servicos",
    Componente.ASSINATURA_INICIAL.value: "assinatura", Componente.RENOVACAO.value: "assinatura", Componente.CREDITOS.value: "creditos",
}


def _dentro(dia: date, inicio: date | None, fim: date | None) -> bool:
    return (inicio is None or dia >= inicio) and (fim is None or dia < fim)


def _f(valor: Decimal) -> float:
    return float(valor.quantize(Decimal("0.01")))


def _comissoes(lista: list[ComissaoRepresentante]) -> dict:
    validas = [c for c in lista if c.status != "estornada"]
    soma = lambda itens: sum((Decimal(str(c.valor_comissao)) for c in itens), ZERO)  # noqa: E731
    por = defaultdict(lambda: defaultdict(Decimal))
    for c in validas:
        for chave, valor in (("representante", c.representante_id), ("contrato", c.contrato_governo_id), ("cliente", c.tenant_id)):
            por[chave][valor] += Decimal(str(c.valor_comissao))
    return {
        "inicial": _f(soma(c for c in validas if c.componente_tipo != Componente.RENOVACAO.value)),
        "renovacao": _f(soma(c for c in validas if c.componente_tipo == Componente.RENOVACAO.value)),
        "reconhecida": _f(soma(validas)), "paga": _f(soma(c for c in validas if c.status == "paga")),
        "pendente": _f(soma(c for c in validas if c.status in ("calculada", "falhou"))),
        # D-073: aguardam as alíquotas de impostos e infraestrutura (valor ainda não calculado)
        "aguardando_parametros": len([c for c in validas if c.status == comissao_service.PENDENTE]),
        "base_bruta_aguardando": _f(sum((Decimal(str(c.base_bruta or 0)) for c in validas if c.status == comissao_service.PENDENTE), ZERO)),
        "a_compensar": _f(soma(c for c in validas if c.status == "a_compensar")),
        **{f"por_{chave}": [{"id": k, "valor": _f(v)} for k, v in sorted(valores.items(), key=lambda i: str(i[0]))]
           for chave, valores in por.items()},
    }


def metricas(db: Session, inicio: date | None = None, fim: date | None = None, tenant_id: str | None = None) -> dict:
    hoje = datetime.now(UTC).date()
    filtro = {"tenant_id": tenant_id} if tenant_id else {}
    contratos = db.query(ContratoGoverno).filter_by(**filtro).all()
    planos = {p.id: p.nome for p in db.query(Plano).filter(Plano.id.in_({c.plano_id for c in contratos} or {0}))}
    componentes = [c for c in db.query(ComponenteContratoGoverno).filter_by(**filtro).all() if not c.cancelado]
    recebimentos = [r for r in db.query(RecebimentoGoverno).filter_by(**filtro).all() if r.estornado_em is None]
    no_periodo = [c for c in componentes if _dentro(c.booking_em, inicio, fim)]

    bookings = defaultdict(Decimal)
    por_produto = defaultdict(Decimal)
    contrato_plano = {c.id: planos.get(c.plano_id) for c in contratos}
    for componente in no_periodo:
        bookings[GRUPO_BOOKING[componente.tipo]] += Decimal(str(componente.valor))
        por_produto[contrato_plano.get(componente.contrato_id)] += Decimal(str(componente.valor))
    tcv_inicial = sum((Decimal(str(c.valor)) for c in no_periodo if c.tipo in (Componente.LICENCA, Componente.IMPLANTACAO,
                                                                               Componente.ASSINATURA_INICIAL)), ZERO)
    ativos = {c.id for c in contratos if c.status == "ATIVO"}
    arr = sum((Decimal(str(p.valor_assinatura)) for p in db.query(PeriodoAssinaturaGoverno).filter_by(status="ATIVO", **filtro)
               if p.contrato_id in ativos and p.inicio <= hoje < p.fim), ZERO)

    comissionavel = {c.id: c.comissionavel for c in componentes}
    cash_in = [r for r in recebimentos if _dentro(r.recebido_em, inicio, fim)]
    total_cash_in = sum((Decimal(str(r.valor)) for r in cash_in), ZERO)
    receita_comissionavel = sum((Decimal(str(r.valor)) for r in cash_in if comissionavel.get(r.componente_id)), ZERO)
    comissoes_consulta = db.query(ComissaoRepresentante).filter(ComissaoRepresentante.contrato_governo_id.isnot(None))
    if tenant_id:
        comissoes_consulta = comissoes_consulta.filter_by(tenant_id=tenant_id)
    comissoes = [c for c in comissoes_consulta.all()
                 if c.criado_em is None or _dentro(c.criado_em.date(), inicio, fim)]
    return {
        "periodo": {"inicio": inicio.isoformat() if inicio else None, "fim": fim.isoformat() if fim else None},
        "bookings": {"licenca": _f(bookings["licenca"]), "servicos": _f(bookings["servicos"]), "assinatura": _f(bookings["assinatura"]),
                     "creditos": _f(bookings["creditos"]), "total": _f(sum(bookings.values(), ZERO))},
        "new_arr": _f(sum((Decimal(str(c.valor)) for c in no_periodo if c.tipo == Componente.ASSINATURA_INICIAL), ZERO)),
        "renewal_arr": _f(sum((Decimal(str(c.valor)) for c in no_periodo if c.tipo == Componente.RENOVACAO), ZERO)),
        "arr_governo": _f(arr), "tcv_inicial": _f(tcv_inicial), "tcv": _f(sum(bookings.values(), ZERO)),
        "cash_in": _f(total_cash_in), "receita_comissionavel": _f(receita_comissionavel),
        "receita_nao_comissionavel": _f(total_cash_in - receita_comissionavel),
        "bookings_por_produto": [{"produto": k, "valor": _f(v)} for k, v in por_produto.items()],
        "comissoes": _comissoes(comissoes),
        "pipeline": pipeline.resumo(db) if tenant_id is None else None,
        "contratos_ativos": len(ativos),
    }


def margem_contribuicao(db: Session, tenant_id: str, inicio: date, fim: date) -> dict:
    """MAP: Receita bruta (Cash-In) − impostos − comissões − custo de IA − infraestrutura. Parte desconhecida fica
    como None e a margem sai `parcial`, nunca com número inventado."""
    dados = metricas(db, inicio, fim, tenant_id)
    bruta = Decimal(str(dados["cash_in"]))
    aliquotas = comissao_service.aliquotas(db)  # D-073: as mesmas alíquotas da base líquida das comissões

    def _deducao(nome: str) -> Decimal | None:
        return (bruta * Decimal(str(aliquotas[nome]))).quantize(Decimal("0.01")) if aliquotas[nome] is not None else None

    impostos, infraestrutura = _deducao("impostos"), _deducao("infraestrutura")
    kpis = finops.economia.kpis(db, datetime.combine(inicio, time.min), datetime.combine(fim, time.min), tenant_id)
    custo_ia = kpis["ai_variable_cost_brl"]
    partes = {"impostos": impostos, "comissoes_iniciais": Decimal(str(dados["comissoes"]["inicial"])),
              "comissoes_renovacao": Decimal(str(dados["comissoes"]["renovacao"])),
              "custo_ia": Decimal(str(custo_ia)) if custo_ia is not None else None, "infraestrutura": infraestrutura}
    conhecidas = sum((v for v in partes.values() if v is not None), ZERO)
    return {
        "tenant_id": tenant_id, "periodo": dados["periodo"], "receita_bruta": _f(bruta),
        **{chave: (_f(valor) if valor is not None else None) for chave, valor in partes.items()},
        "margem_contribuicao": _f(bruta - conhecidas), "parcial": any(v is None for v in partes.values()),
        "desconhecidos": [chave for chave, valor in partes.items() if valor is None],
        "contrato": contratos_mod.do_tenant(db, tenant_id) is not None,
    }
