"""Infrastructure Cost Model (D-074): custo de infraestrutura atribuível a uma receita.

Componentes combináveis (um só = método simples; vários = HYBRID): percentual da receita, valor fixo por recebimento,
percentual por tenant, percentual por produto/segmento e custo real de IA do tenant (ledger do AI Gateway). O custo de IA
só entra por `USO_IA` — se um percentual já o inclui, não use `USO_IA` (evita contar duas vezes). Cada recebimento consome o
custo de IA ainda não atribuído do tenant (marca d'água `custo_ia_ate`), então parcelas não repetem o mesmo custo.
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import COMPONENTES_INFRA
from app.models.apuracao_comissao import ApuracaoComissao, ModeloCustoInfra
from app.models.creditos_ia import ExecucaoIa
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

CENTAVO = Decimal("0.01")


def aplicavel(db: Session, dia: date) -> ModeloCustoInfra | None:
    return (db.query(ModeloCustoInfra).filter(ModeloCustoInfra.vigente_de <= dia,
                                              or_(ModeloCustoInfra.vigente_ate.is_(None), ModeloCustoInfra.vigente_ate > dia))
            .order_by(ModeloCustoInfra.vigente_de.desc(), ModeloCustoInfra.id.desc()).first())


def custo_ia_brl(db: Session, tenant_id: str, inicio: datetime, fim: datetime) -> Decimal | None:
    """Custo real de IA do tenant no intervalo (execuções liquidadas pelo AI Gateway). None = desconhecido (sem câmbio
    ou modelo sem preço)."""
    execucoes = db.query(ExecucaoIa.custo_total_brl).filter(
        ExecucaoIa.tenant_id == tenant_id, ExecucaoIa.criado_em >= inicio, ExecucaoIa.criado_em < fim,
        ExecucaoIa.status.in_(("LIQUIDADA", "ESTORNADA", "LIBERADA"))).all()
    if any(custo is None for (custo,) in execucoes):
        return None
    return sum((Decimal(str(custo)) for (custo,) in execucoes), Decimal(0)).quantize(CENTAVO, ROUND_HALF_UP)


def _percentual(mapa: dict, chaves: tuple, padrao) -> float | None:
    for chave in chaves:
        if chave in (mapa or {}):
            return mapa[chave]
    return padrao


def alocar(db: Session, modelo: ModeloCustoInfra, apuracao: ApuracaoComissao) -> tuple[Decimal | None, dict]:
    """(custo atribuível ou None se algum dado faltar, detalhe por componente)."""
    bruto = Decimal(str(apuracao.receita_bruta))
    total, detalhe = Decimal(0), []
    for componente in modelo.componentes:
        tipo = componente["tipo"]
        valor: Decimal | None
        if tipo == "PERCENTUAL":
            valor = bruto * Decimal(str(componente["percentual"]))
        elif tipo == "FIXO_POR_RECEBIMENTO":
            valor = Decimal(str(componente["valor"]))
        elif tipo == "POR_TENANT":
            pct = _percentual(componente.get("percentuais"), (apuracao.tenant_id,), componente.get("padrao"))
            valor = bruto * Decimal(str(pct)) if pct is not None else None
        elif tipo == "POR_PRODUTO":
            pct = _percentual(componente.get("percentuais"), (apuracao.produto, apuracao.segmento), componente.get("padrao"))
            valor = bruto * Decimal(str(pct)) if pct is not None else None
        elif tipo == "USO_IA":
            fim = datetime.combine(apuracao.recebido_em + timedelta(days=1), datetime.min.time())
            ultimo = db.query(func.max(ApuracaoComissao.custo_ia_ate)).filter(
                ApuracaoComissao.tenant_id == apuracao.tenant_id, ApuracaoComissao.id != apuracao.id,
                ApuracaoComissao.custo_ia_ate.isnot(None)).scalar()
            inicio = ultimo or fim - timedelta(days=int(componente.get("janela_dias") or 30))
            valor = custo_ia_brl(db, apuracao.tenant_id, inicio, fim) if fim > inicio else Decimal(0)
            apuracao.custo_ia = valor
            apuracao.custo_ia_ate = fim if valor is not None else None
        else:
            valor = None
        valor = valor.quantize(CENTAVO, ROUND_HALF_UP) if valor is not None else None
        detalhe.append({"tipo": tipo, "valor": float(valor) if valor is not None else None})
        if valor is None:
            return None, {"componentes": detalhe}
        total += valor
    return total.quantize(CENTAVO, ROUND_HALF_UP), {"componentes": detalhe}


def criar(db: Session, dados: dict, ator_id: str | None) -> ModeloCustoInfra:
    componentes = dados.get("componentes") or []
    if not componentes or any(c.get("tipo") not in COMPONENTES_INFRA for c in componentes):
        raise ValidacaoFalhou(f"Componentes de infraestrutura: {', '.join(COMPONENTES_INFRA)}.")
    tipos = [c["tipo"] for c in componentes]
    if tipos.count("USO_IA") > 1:
        raise ValidacaoFalhou("Custo de IA só pode entrar uma vez (evita dupla contagem).")
    for c in componentes:
        valores = ([c.get("percentual")] if c["tipo"] == "PERCENTUAL" else list((c.get("percentuais") or {}).values()) + [c.get("padrao")]
                   if c["tipo"] in ("POR_TENANT", "POR_PRODUTO") else [])
        if any(v is not None and not 0 <= float(v) < 1 for v in valores) or (c["tipo"] == "PERCENTUAL" and c.get("percentual") is None):
            raise ValidacaoFalhou("Percentuais de infraestrutura entre 0 e 1.")
        if c["tipo"] == "FIXO_POR_RECEBIMENTO" and (c.get("valor") is None or float(c["valor"]) < 0):
            raise ValidacaoFalhou("Valor fixo por recebimento precisa ser informado e não negativo.")
    vigente_de, vigente_ate = dados["vigente_de"], dados.get("vigente_ate")
    for aberto in db.query(ModeloCustoInfra).filter_by(vigente_ate=None).all():
        if aberto.vigente_de >= vigente_de:
            raise ValidacaoFalhou(f"Já existe modelo vigente desde {aberto.vigente_de}; encerre-o antes.")
        aberto.vigente_ate = vigente_de
    metodo = COMPONENTES_INFRA[tipos[0]] if len(tipos) == 1 else "HYBRID"
    modelo = ModeloCustoInfra(nome=dados["nome"], vigente_de=vigente_de, vigente_ate=vigente_ate, metodo=metodo, componentes=componentes,
                              fonte=dados.get("fonte"), observacoes=dados.get("observacoes"), criado_por=ator_id)
    db.add(modelo)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "modelo_custo_infra_criado", "modelo_custo_infra", modelo.id,
                                ator_id, {"nome": modelo.nome, "vigente_de": str(vigente_de), "metodo": metodo, "componentes": componentes,
                                          "origem": "admin"})
    return modelo


def como_dict(modelo: ModeloCustoInfra) -> dict:
    return {"id": modelo.id, "nome": modelo.nome, "vigente_de": modelo.vigente_de.isoformat(),
            "vigente_ate": modelo.vigente_ate.isoformat() if modelo.vigente_ate else None, "metodo": modelo.metodo,
            "componentes": modelo.componentes, "fonte": modelo.fonte, "observacoes": modelo.observacoes}
