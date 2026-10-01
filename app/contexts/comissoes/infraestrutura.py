"""Infrastructure Cost Model (D-074, D-075): custo de infraestrutura atribuível a uma receita.

Cada componente é uma categoria de custo (cloud, banco, armazenamento, rede, observabilidade, terceiros e infraestrutura
de IA alocada) alocada por um método: FIXED, PERCENTAGE, PER_TENANT, PER_USER ou USAGE_BASED (vários componentes =
HYBRID). Os valores são do PO; nenhum fica no código. Sem modelo vigente, a comissão aguarda (AWAITING_INFRASTRUCTURE_COST).

Custo de IA: só pela categoria `allocated_ai_infrastructure_cost` com USAGE_BASED (custo real do ledger do AI Gateway,
USD × cotação aplicável) e só quando a Commission Policy da margem manda deduzir IA — se outro componente já embute IA,
não use os dois (dupla contagem). Cada recebimento consome o custo ainda não atribuído do tenant (marca d'água
`custo_ia_ate`), então parcelas não repetem o mesmo custo.
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.contexts.comissoes.tipos import CATEGORIA_IA, CATEGORIAS_INFRA, METODO_HIBRIDO, METODOS_INFRA, Faltante
from app.contexts.finops import contract as finops
from app.models.apuracao_comissao import ApuracaoComissao, ModeloCustoInfra
from app.models.creditos_ia import ExecucaoIa
from app.models.usuario import Usuario
from app.services import auditoria_service
from app.services.errors import ValidacaoFalhou

CENTAVO = Decimal("0.01")


def aplicavel(db: Session, dia: date) -> ModeloCustoInfra | None:
    return (db.query(ModeloCustoInfra).filter(ModeloCustoInfra.vigente_de <= dia,
                                              or_(ModeloCustoInfra.vigente_ate.is_(None), ModeloCustoInfra.vigente_ate > dia))
            .order_by(ModeloCustoInfra.vigente_de.desc(), ModeloCustoInfra.id.desc()).first())


def custo_ia_brl(db: Session, tenant_id: str, inicio: datetime, fim: datetime) -> tuple[Decimal | None, str | None]:
    """(custo real de IA do tenant no intervalo, motivo se desconhecido). Execução sem custo em reais é convertida pela
    cotação USD/BRL vigente no instante dela; sem cotação → FX_RATE; modelo sem preço → INFRASTRUCTURE_COST."""
    execucoes = db.query(ExecucaoIa).filter(
        ExecucaoIa.tenant_id == tenant_id, ExecucaoIa.criado_em >= inicio, ExecucaoIa.criado_em < fim,
        ExecucaoIa.status.in_(("LIQUIDADA", "ESTORNADA", "LIBERADA"))).all()
    total = Decimal(0)
    for execucao in execucoes:
        if execucao.custo_desconhecido:
            return None, Faltante.CUSTO_INFRA.value
        if execucao.custo_total_brl is not None:
            total += Decimal(str(execucao.custo_total_brl))
            continue
        taxa = finops.cambio.taxa(db, "USD", "BRL", execucao.criado_em)
        if taxa is None:
            return None, Faltante.CAMBIO.value
        total += Decimal(str(execucao.custo_total_usd or 0)) * taxa
    return total.quantize(CENTAVO, ROUND_HALF_UP), None


def _por_chave(mapa: dict | None, chaves: tuple, padrao):
    for chave in chaves:
        if chave in (mapa or {}):
            return mapa[chave]
    return padrao


def _custo_ia(db: Session, componente: dict, apuracao: ApuracaoComissao) -> tuple[Decimal | None, str | None]:
    fim = datetime.combine(apuracao.recebido_em + timedelta(days=1), datetime.min.time())
    ultimo = db.query(func.max(ApuracaoComissao.custo_ia_ate)).filter(
        ApuracaoComissao.tenant_id == apuracao.tenant_id, ApuracaoComissao.id != apuracao.id,
        ApuracaoComissao.custo_ia_ate.isnot(None)).scalar()
    inicio = ultimo or fim - timedelta(days=int(componente.get("janela_dias") or 30))
    valor, motivo = custo_ia_brl(db, apuracao.tenant_id, inicio, fim) if fim > inicio else (Decimal(0), None)
    apuracao.custo_ia = valor
    apuracao.custo_ia_ate = fim if valor is not None else None
    return valor, motivo


def alocar(db: Session, modelo: ModeloCustoInfra, apuracao: ApuracaoComissao, deduzir_custo_ia: bool = False) -> tuple[Decimal | None, dict]:
    """(custo atribuível ou None se algum valor faltar, detalhe por componente). O detalhe traz `faltante` (FX_RATE ou
    INFRASTRUCTURE_COST) quando o custo não pôde ser calculado."""
    bruto = Decimal(str(apuracao.receita_bruta))
    apuracao.custo_ia = apuracao.custo_ia_ate = None
    total, detalhe = Decimal(0), []
    componentes = list(modelo.componentes)
    if deduzir_custo_ia and not any(c.get("categoria") == CATEGORIA_IA for c in componentes):
        componentes.append({"categoria": CATEGORIA_IA, "metodo": "USAGE_BASED"})  # política manda deduzir: custo real medido
    for componente in componentes:
        categoria, metodo = componente.get("categoria"), componente.get("metodo")
        valor: Decimal | None
        motivo = None
        if categoria == CATEGORIA_IA and not deduzir_custo_ia:
            detalhe.append({"categoria": categoria, "metodo": metodo, "valor": 0.0, "observacao": "fora da Commission Policy"})
            continue
        if metodo == "FIXED":
            valor = Decimal(str(componente["valor"]))
        elif metodo == "PERCENTAGE":
            pct = componente.get("percentual")
            if pct is None:
                pct = _por_chave(componente.get("percentuais"), (apuracao.produto, apuracao.segmento), componente.get("padrao"))
            valor = bruto * Decimal(str(pct)) if pct is not None else None
        elif metodo == "PER_TENANT":
            por_tenant = _por_chave(componente.get("valores"), (apuracao.tenant_id,), componente.get("padrao"))
            valor = Decimal(str(por_tenant)) if por_tenant is not None else None
        elif metodo == "PER_USER":
            usuarios = db.query(func.count(Usuario.id)).filter(Usuario.tenant_id == apuracao.tenant_id, Usuario.ativo.is_(True)).scalar()
            valor = Decimal(str(componente["valor_por_usuario"])) * Decimal(usuarios or 0)
        elif metodo == "USAGE_BASED" and categoria == CATEGORIA_IA:
            valor, motivo = _custo_ia(db, componente, apuracao)
        else:
            valor = None
        valor = valor.quantize(CENTAVO, ROUND_HALF_UP) if valor is not None else None
        detalhe.append({"categoria": categoria, "metodo": metodo, "valor": float(valor) if valor is not None else None})
        if valor is None:
            return None, {"componentes": detalhe, "faltante": motivo or Faltante.CUSTO_INFRA.value}
        total += valor
    return total.quantize(CENTAVO, ROUND_HALF_UP), {"componentes": detalhe}


def _validar(componentes: list[dict]) -> None:
    if not componentes:
        raise ValidacaoFalhou("Informe ao menos um componente de custo.")
    for c in componentes:
        categoria, metodo = c.get("categoria"), c.get("metodo")
        if categoria not in CATEGORIAS_INFRA or metodo not in METODOS_INFRA:
            raise ValidacaoFalhou(f"Categoria: {', '.join(CATEGORIAS_INFRA)}. Método: {', '.join(METODOS_INFRA)}.")
        if metodo == "USAGE_BASED" and categoria != CATEGORIA_IA:
            raise ValidacaoFalhou("USAGE_BASED só existe para a infraestrutura de IA (único custo medido por uso na plataforma).")
        percentuais = [c.get("percentual"), c.get("padrao") if metodo == "PERCENTAGE" else None,
                       *((c.get("percentuais") or {}).values())]
        if metodo == "PERCENTAGE" and (any(v is not None and not 0 <= float(v) < 1 for v in percentuais)
                                       or (c.get("percentual") is None and not c.get("percentuais"))):
            raise ValidacaoFalhou("PERCENTAGE: percentual (ou percentuais por produto) entre 0 e 1.")
        valores = {"FIXED": [c.get("valor")], "PER_USER": [c.get("valor_por_usuario")],
                   "PER_TENANT": [*(c.get("valores") or {}).values(), c.get("padrao")]}.get(metodo, [])
        if metodo in ("FIXED", "PER_USER") and valores[0] is None:
            raise ValidacaoFalhou(f"{metodo}: informe o valor.")
        if metodo == "PER_TENANT" and not c.get("valores") and c.get("padrao") is None:
            raise ValidacaoFalhou("PER_TENANT: informe valores por tenant ou o padrão.")
        if any(v is not None and float(v) < 0 for v in valores):
            raise ValidacaoFalhou("Custos não podem ser negativos.")
    if sum(c["categoria"] == CATEGORIA_IA for c in componentes) > 1:
        raise ValidacaoFalhou("Custo de IA só pode entrar uma vez (evita dupla contagem).")


def criar(db: Session, dados: dict, ator_id: str | None) -> ModeloCustoInfra:
    componentes = dados.get("componentes") or []
    _validar(componentes)
    vigente_de, vigente_ate = dados["vigente_de"], dados.get("vigente_ate")
    for aberto in db.query(ModeloCustoInfra).filter_by(vigente_ate=None).all():
        if aberto.vigente_de >= vigente_de:
            raise ValidacaoFalhou(f"Já existe modelo vigente desde {aberto.vigente_de}; encerre-o antes.")
        aberto.vigente_ate = vigente_de
    metodo = componentes[0]["metodo"] if len(componentes) == 1 else METODO_HIBRIDO
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
