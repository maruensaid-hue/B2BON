"""Waterfall financeira das comissões (D-074), para o MAP:

    Receita bruta → impostos → infraestrutura → Margem Comissionável Líquida → comissão → margem CyberFort após comissão

Por venda, representante, produto, tenant ou período. Recebimentos ainda sem parâmetros de custo não entram nos totais
(seriam números inventados): aparecem separados em `aguardando`.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import Status
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.comissao_representante import ComissaoRepresentante

AGRUPAMENTOS = ("venda", "representante", "produto", "tenant", "periodo")
CAMPOS = ("receita_bruta", "impostos", "infraestrutura", "margem_comissionavel_liquida", "comissao")


def _chave(agrupar: str, apuracao: ApuracaoComissao, representante_id: int | None):
    return {"venda": apuracao.id, "representante": representante_id, "produto": apuracao.produto, "tenant": apuracao.tenant_id,
            "periodo": apuracao.recebido_em.strftime("%Y-%m")}[agrupar]


def _linha(chave, valores: dict, aguardando: Decimal) -> dict:
    bruta = valores["receita_bruta"]
    apos = valores["margem_comissionavel_liquida"] - valores["comissao"]
    pct = lambda v: float((v / bruta * 100).quantize(Decimal("0.01"))) if bruta else None  # noqa: E731
    return {
        "chave": chave, **{c: float(valores[c]) for c in CAMPOS}, "margem_cyberfort_apos_comissao": float(apos),
        "percentuais": {"impostos": pct(valores["impostos"]), "infraestrutura": pct(valores["infraestrutura"]),
                        "margem_comissionavel_liquida": pct(valores["margem_comissionavel_liquida"]), "comissao": pct(valores["comissao"]),
                        "margem_cyberfort_apos_comissao": pct(apos)},
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
    for apuracao in consulta.all():
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
                "margem_comissionavel_liquida": Decimal(str(apuracao.margem_comissionavel_liquida)) * fracao,
                "comissao": sum((Decimal(str(c.valor_comissao)) for c in comissoes
                                 if comissao and c.representante_id == comissao.representante_id), Decimal(0)),
            }
            for campo, valor in valores.items():
                grupos[chave][campo] += valor
                totais[campo] += valor
    return {"agrupar": agrupar, "periodo": {"inicio": inicio.isoformat() if inicio else None, "fim": fim.isoformat() if fim else None},
            "linhas": [_linha(chave, valores, aguardando[chave]) for chave, valores in sorted(grupos.items(), key=lambda i: str(i[0]))],
            "total": _linha("total", totais, total_aguardando)}
