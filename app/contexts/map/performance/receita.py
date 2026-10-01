"""Receita do representante para o MAP Performance (D-080): New MRR, carteira (adimplência) e comissão recorrente.

- New MRR = 1ª mensalidade aprovada de um cliente novo atribuído ao representante (`Tenant.representante_id`),
  só do segmento PRIVATE. Government Bookings nunca entram aqui (pipeline e bookings governamentais ficam à parte).
- Comissão = a do Commission Engine (D-074): só mensalidade efetivamente paga gera comissão; o MAP só lê e agrega.
- Carteira: ADIMPLENTE, INADIMPLENTE (sem mensalidade paga há mais de ciclo + tolerância) ou CANCELADO (sem licença
  ativa). Com a política de inadimplência HOLD, a comissão a pagar de cliente inadimplente fica retida.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session

from app.contexts.map.performance.tipos import Familia, SituacaoCarteira
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.comissao_representante import ComissaoRepresentante
from app.models.licenca import Licenca
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.tenant import Tenant

STATUS_SEM_VALOR = ("REVERSED", "FAILED")


def classificar_plano(plano: Plano | None, regras: list[dict]) -> str:
    """Família do produto pela 1ª regra da política que casa (segmento, categoria ou módulo contratado)."""
    if plano is None:
        return Familia.NAO_CLASSIFICADA.value
    modulos = set(plano.modulos_contratados or [])
    for regra in regras:
        if ("segmento" in regra and plano.segmento == regra["segmento"]) or ("categoria" in regra and plano.categoria == regra["categoria"]) \
                or ("modulo" in regra and regra["modulo"] in modulos):
            return regra["familia"]
    return Familia.NAO_CLASSIFICADA.value


def _primeiros_pagamentos(db: Session):
    return (db.query(PagamentoLicenca.tenant_id.label("tenant_id"), func.min(PagamentoLicenca.confirmado_em).label("primeiro_em"))
            .filter(PagamentoLicenca.status == "aprovado", PagamentoLicenca.confirmado_em.isnot(None))
            .group_by(PagamentoLicenca.tenant_id).subquery())


def novos_clientes(db: Session, representante_ids: list[int], inicio: datetime, fim: datetime, politica: dict) -> list[dict]:
    """Clientes novos (1ª mensalidade paga no período) por representante, com valor e família (1 consulta)."""
    if not representante_ids:
        return []
    primeiro = _primeiros_pagamentos(db)
    linhas = (db.query(Tenant.representante_id, Tenant.id, Tenant.razao_social, PagamentoLicenca.valor, PagamentoLicenca.confirmado_em, Plano)
              .join(primeiro, primeiro.c.tenant_id == Tenant.id)
              .join(PagamentoLicenca, and_(PagamentoLicenca.tenant_id == Tenant.id, PagamentoLicenca.confirmado_em == primeiro.c.primeiro_em,
                                           PagamentoLicenca.status == "aprovado"))
              .join(Plano, Plano.id == PagamentoLicenca.plano_id)
              .filter(Tenant.representante_id.in_(representante_ids), primeiro.c.primeiro_em >= inicio, primeiro.c.primeiro_em < fim)
              .all())
    vistos, clientes = set(), []
    for representante_id, tenant_id, nome, valor, em, plano in linhas:
        if tenant_id in vistos or plano.segmento != "PRIVATE":  # Government nunca é New MRR
            continue
        vistos.add(tenant_id)
        clientes.append({"representante_id": representante_id, "tenant_id": tenant_id, "cliente": nome, "valor": float(valor or 0),
                         "primeiro_pagamento_em": em, "plano": plano.nome,
                         "familia": classificar_plano(plano, politica["classificacao_planos"])})
    return clientes


def carteira(db: Session, representante_ids: list[int], hoje: date, politica_comissao: dict) -> list[dict]:
    """Situação de cada cliente da carteira (1 consulta)."""
    if not representante_ids:
        return []
    regra = politica_comissao["inadimplencia"]
    limite = datetime.combine(hoje - timedelta(days=regra["ciclo_dias"] + regra["tolerancia_dias"]), datetime.min.time())
    ultimo = (db.query(PagamentoLicenca.tenant_id.label("tenant_id"), func.max(PagamentoLicenca.confirmado_em).label("ultimo_em"))
              .filter(PagamentoLicenca.status == "aprovado").group_by(PagamentoLicenca.tenant_id).subquery())
    licenca_ativa = exists().where(Licenca.tenant_id == Tenant.id, Licenca.status == "ativa")
    linhas = (db.query(Tenant.representante_id, Tenant.id, Tenant.razao_social, Tenant.ativo, ultimo.c.ultimo_em, licenca_ativa)
              .join(ultimo, ultimo.c.tenant_id == Tenant.id).filter(Tenant.representante_id.in_(representante_ids)).all())
    resultado = []
    for representante_id, tenant_id, nome, ativo, ultimo_em, ativa in linhas:
        if not ativo or not ativa:
            situacao = SituacaoCarteira.CANCELADO
        elif ultimo_em < limite:
            situacao = SituacaoCarteira.INADIMPLENTE
        else:
            situacao = SituacaoCarteira.ADIMPLENTE
        resultado.append({"representante_id": representante_id, "tenant_id": tenant_id, "cliente": nome, "situacao": situacao.value,
                          "ultimo_pagamento_em": ultimo_em})
    return resultado


def tenants_inadimplentes(db: Session, tenant_ids: list[int | str], hoje: date, politica_comissao: dict) -> set[str]:
    """Clientes com comissão retida pela política (HOLD) — usado pelo repasse antes de pagar."""
    if not tenant_ids or politica_comissao["inadimplencia"]["acao"] != "HOLD":
        return set()
    regra = politica_comissao["inadimplencia"]
    limite = datetime.combine(hoje - timedelta(days=regra["ciclo_dias"] + regra["tolerancia_dias"]), datetime.min.time())
    ultimos = dict(db.query(PagamentoLicenca.tenant_id, func.max(PagamentoLicenca.confirmado_em))
                   .filter(PagamentoLicenca.status == "aprovado", PagamentoLicenca.tenant_id.in_(tenant_ids))
                   .group_by(PagamentoLicenca.tenant_id).all())
    return {t for t in tenant_ids if ultimos.get(t) is not None and ultimos[t] < limite}  # sem pagamento registrado: nada a provar


def comissoes(db: Session, representante_ids: list[int], desde: date | None = None, ate: date | None = None) -> list[dict]:
    """Comissões privadas recorrentes do Commission Engine (1 consulta): competência, cliente, produto e status."""
    if not representante_ids:
        return []
    query = (db.query(ComissaoRepresentante.id, ComissaoRepresentante.representante_id, ComissaoRepresentante.tenant_id, Tenant.razao_social,
                      ApuracaoComissao.produto, ApuracaoComissao.recebido_em, ComissaoRepresentante.valor_comissao,
                      ComissaoRepresentante.status, ComissaoRepresentante.pago_em)
             .join(ApuracaoComissao, ApuracaoComissao.id == ComissaoRepresentante.apuracao_id)
             .join(Tenant, Tenant.id == ComissaoRepresentante.tenant_id)
             .filter(ComissaoRepresentante.representante_id.in_(representante_ids), ComissaoRepresentante.pagamento_licenca_id.isnot(None)))
    if desde is not None:
        query = query.filter(ApuracaoComissao.recebido_em >= desde)
    if ate is not None:
        query = query.filter(ApuracaoComissao.recebido_em <= ate)
    return [{"id": i, "representante_id": r, "tenant_id": t, "cliente": nome, "produto": produto, "competencia": recebido.strftime("%Y-%m"),
             "recebido_em": recebido, "valor": float(valor or 0), "status": status, "pago_em": pago}
            for i, r, t, nome, produto, recebido, valor, status, pago in query.all()]


def resumo_comissao(linhas: list[dict], situacoes: dict[str, str], politica_comissao: dict) -> dict:
    """Realizada (PAID), a receber (PAYABLE/ACCRUED/CALCULATED), retida por inadimplência (HOLD) e aguardando parâmetros."""
    hold = politica_comissao["inadimplencia"]["acao"] == "HOLD"
    resumo = {"realizada": 0.0, "a_receber": 0.0, "retida_inadimplencia": 0.0, "aguardando_parametros": 0,
              "por_competencia": defaultdict(float), "por_cliente": defaultdict(float), "por_produto": defaultdict(float)}
    for linha in linhas:
        if linha["status"] in STATUS_SEM_VALOR:
            continue
        if linha["status"] == "AWAITING_COST_PARAMETERS":
            resumo["aguardando_parametros"] += 1
            continue
        if linha["status"] == "PAID":
            resumo["realizada"] += linha["valor"]
        elif hold and situacoes.get(linha["tenant_id"]) == SituacaoCarteira.INADIMPLENTE.value:
            resumo["retida_inadimplencia"] += linha["valor"]
        else:
            resumo["a_receber"] += linha["valor"]
        resumo["por_competencia"][linha["competencia"]] += linha["valor"]
        resumo["por_cliente"][linha["cliente"]] += linha["valor"]
        resumo["por_produto"][linha["produto"]] += linha["valor"]
    for chave in ("realizada", "a_receber", "retida_inadimplencia"):
        resumo[chave] = round(resumo[chave], 2)
    for chave in ("por_competencia", "por_cliente", "por_produto"):
        resumo[chave] = {k: round(v, 2) for k, v in sorted(resumo[chave].items())}
    resumo["taxa"] = politica_comissao["taxa"]
    return resumo
