"""Waterfall financeira das comissões (D-074, D-076), para o MAP:

    Receita bruta → impostos → infraestrutura provisionada → Margem Comissionável Líquida → comissão
    → margem CyberFort após comissão

Ao lado, sem esconder a diferença (D-076): custo real de infraestrutura, custo de IA, Actual Contribution Margin (receita −
impostos − infraestrutura real − IA), Conservative Contribution Margin (receita − impostos − infraestrutura provisionada −
IA) e a reserva de infraestrutura (provisionado − real).

Por venda, representante, produto, tenant ou período. Recebimentos ainda sem parâmetros de custo não entram nos totais
(seriam números inventados): aparecem separados em `aguardando`, com a contagem por parâmetro faltante. O total traz os
impostos por tributo (D-075), como o Tax Engine os calculou.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.comissoes import tributos
from app.contexts.comissoes.motor import status_valor
from app.contexts.comissoes.tipos import Status
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.comissao_representante import ComissaoRepresentante

AGRUPAMENTOS = ("venda", "representante", "produto", "tenant", "periodo")
CAMPOS = ("receita_bruta", "impostos", "infraestrutura", "infraestrutura_real", "custo_ia", "margem_comissionavel_liquida", "comissao")


def _chave(agrupar: str, apuracao: ApuracaoComissao, representante_id: int | None):
    return {"venda": apuracao.id, "representante": representante_id, "produto": apuracao.produto, "tenant": apuracao.tenant_id,
            "periodo": apuracao.recebido_em.strftime("%Y-%m")}[agrupar]


def _linha(chave, valores: dict, aguardando: Decimal, real_incompleto: bool = False) -> dict:
    bruta = valores["receita_bruta"]
    apos = valores["margem_comissionavel_liquida"] - valores["comissao"]
    base = bruta - valores["impostos"] - valores["custo_ia"]
    real = None if real_incompleto else base - valores["infraestrutura_real"]
    conservadora = base - valores["infraestrutura"]
    reserva = None if real_incompleto else valores["infraestrutura"] - valores["infraestrutura_real"]
    pct = lambda v: float((v / bruta * 100).quantize(Decimal("0.01"))) if bruta and v is not None else None  # noqa: E731
    return {
        "chave": chave, **{c: float(valores[c]) for c in CAMPOS}, "margem_cyberfort_apos_comissao": float(apos),
        "margem_contribuicao_real": float(real) if real is not None else None,
        "margem_contribuicao_conservadora": float(conservadora), "reserva_infraestrutura": float(reserva) if reserva is not None else None,
        "infraestrutura_real_incompleta": real_incompleto,
        "percentuais": {"impostos": pct(valores["impostos"]), "infraestrutura": pct(valores["infraestrutura"]),
                        "infraestrutura_real": pct(None if real_incompleto else valores["infraestrutura_real"]),
                        "custo_ia": pct(valores["custo_ia"]),
                        "margem_comissionavel_liquida": pct(valores["margem_comissionavel_liquida"]), "comissao": pct(valores["comissao"]),
                        "margem_cyberfort_apos_comissao": pct(apos), "margem_contribuicao_real": pct(real),
                        "margem_contribuicao_conservadora": pct(conservadora)},
        "aguardando_parametros": float(aguardando),
    }


def calcular(db: Session, agrupar: str = "tenant", inicio: date | None = None, fim: date | None = None,
             tenant_id: str | None = None) -> dict:
    if agrupar not in AGRUPAMENTOS:
        agrupar = "tenant"
    consulta = db.query(ApuracaoComissao).filter(ApuracaoComissao.status != Status.ESTORNADA.value)
    if inicio:
        consulta = consulta.filter(ApuracaoComissao.recebido_em >= inicio)
    if fim:
        consulta = consulta.filter(ApuracaoComissao.recebido_em < fim)
    if tenant_id:
        consulta = consulta.filter(ApuracaoComissao.tenant_id == tenant_id)
    grupos = defaultdict(lambda: dict.fromkeys(CAMPOS, Decimal(0)))
    aguardando = defaultdict(Decimal)
    totais, total_aguardando = dict.fromkeys(CAMPOS, Decimal(0)), Decimal(0)
    por_tributo, por_parametro = defaultdict(Decimal), defaultdict(int)
    reforma = defaultdict(Decimal)
    taxas_teste: dict[str, float] = {}
    real_incompleto, total_real_incompleto = set(), False
    for apuracao in consulta.all():
        if apuracao.status == Status.CALCULADA.value:
            for linha in ((apuracao.detalhe or {}).get("tributos") or {}).get("tributos") or []:
                por_tributo[linha["tributo"]] += Decimal(str(linha.get("valor") or 0))
            snapshot = ((apuracao.detalhe or {}).get("tributos") or {}).get("reforma") or {}
            for chave in ("cbs_nominal_test_tax", "ibs_nominal_test_tax", "cbs_cash_tax", "ibs_cash_tax", "pis_cofins_offset"):
                reforma[chave] += Decimal(str(snapshot.get(chave) or 0))
            for chave in ("cbs_test_rate", "ibs_test_rate"):
                if snapshot.get(chave) is not None:
                    taxas_teste[chave] = snapshot[chave]
        else:
            por_parametro[status_valor(apuracao)] += 1
        comissoes = [c for c in db.query(ComissaoRepresentante).filter_by(apuracao_id=apuracao.id).all() if c.status != Status.ESTORNADA.value]
        accruals = [c for c in comissoes if c.evento == "ACCRUAL"] or [None]
        for comissao in accruals:
            fracao = Decimal(str(comissao.fracao_divisao or 1)) if comissao else Decimal(1)
            chave = _chave(agrupar, apuracao, comissao.representante_id if comissao else None)
            if apuracao.status != Status.CALCULADA.value:
                parte = Decimal(str(apuracao.receita_bruta)) * fracao
                aguardando[chave] += parte
                total_aguardando += parte
                grupos[chave]  # noqa: B018 — garante a linha
                continue
            valores = {
                "receita_bruta": Decimal(str(apuracao.receita_bruta)) * fracao, "impostos": Decimal(str(apuracao.impostos)) * fracao,
                "infraestrutura": Decimal(str(apuracao.custo_infra)) * fracao,
                "infraestrutura_real": Decimal(str(apuracao.custo_infra_real or 0)) * fracao,
                "custo_ia": Decimal(str(apuracao.custo_ia or 0)) * fracao,
                "margem_comissionavel_liquida": Decimal(str(apuracao.margem_comissionavel_liquida)) * fracao,
                "comissao": sum((Decimal(str(c.valor_comissao)) for c in comissoes
                                 if comissao and c.representante_id == comissao.representante_id), Decimal(0)),
            }
            if apuracao.custo_infra_real is None:
                real_incompleto.add(chave)
                total_real_incompleto = True
            for campo, valor in valores.items():
                grupos[chave][campo] += valor
                totais[campo] += valor
    return {"agrupar": agrupar, "periodo": {"inicio": inicio.isoformat() if inicio else None, "fim": fim.isoformat() if fim else None},
            "linhas": [_linha(chave, valores, aguardando[chave], chave in real_incompleto)
                       for chave, valores in sorted(grupos.items(), key=lambda i: str(i[0]))],
            "total": {**_linha("total", totais, total_aguardando, total_real_incompleto),
                      "impostos_por_tributo": {t: float(v) for t, v in sorted(por_tributo.items())},
                      "aguardando_por_parametro": dict(sorted(por_parametro.items())),
                      "reforma_tributaria": _reforma(db, reforma, taxas_teste)}}


def _reforma(db: Session, valores: dict, taxas: dict) -> dict:
    """CBS/IBS no MAP (D-078): alíquotas-teste e imposto de caixa lado a lado — nunca "CBS = 0%"."""
    periodo = tributos.status_vigente(db, date.today())
    return {**taxas, **{k: float(v) for k, v in valores.items()},
            "status": periodo.status if periodo else None, "status_rotulo": tributos.ROTULOS_SITUACAO.get(periodo.status) if periodo else None,
            "vigente_ate": periodo.vigente_ate.isoformat() if periodo and periodo.vigente_ate else None}
