"""Infrastructure Cost Engine (D-076): custo de infraestrutura atribuível a uma receita, a partir do Infrastructure Cost
Pool (fornecedores/planos cadastrados, nenhum no código).

Dois custos coexistem e nunca se misturam:
- REAL (`custo_real`): o que a CyberFort efetivamente paga — FinOps e Actual Contribution Margin.
- PROVISIONADO: política conservadora. Com `MAX_CONTRACTED_PLAN`, o custo integral do plano de referência (máximo)
  escolhido para o fornecedor, mesmo com uso baixo. É a base da comissão (política de infraestrutura `custo_comissao`).

Alocação mensal do pool:
    unidades ponderadas = Σ tenants ativos × peso do tier do plano (pesos configuráveis na política)
    custo por unidade   = pool provisionado do mês ÷ unidades ponderadas
    custo do tenant     = custo por unidade × peso do tenant + custos diretos medidos do tenant
Componente DIRECT: o consumo medido por tenant vai direto para ele; o restante do plano (provisionado − medido) volta ao
pool ponderado. Componente contabilizado como AI_COST nunca entra aqui (já está no custo de IA do FinOps).

Um recebimento carrega o custo dos meses de operação que remunera (`meses_infra`: mensalidade = 1, subscrição anual =
meses do período × fração recebida; licença, implantação e adicionais = 0), uma vez por tenant-mês. Sem pool com valores,
nenhuma comissão sai de AWAITING_INFRASTRUCTURE_COST.
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.contexts.comissoes import politica
from app.contexts.comissoes.tipos import (
    CATEGORIAS_INFRA,
    CICLOS_COBRANCA,
    Contabilizacao,
    Faltante,
    MetodoAlocacao,
    PoliticaCustoInfra,
)
from app.contexts.finops import contract as finops
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.creditos_ia import ExecucaoIa
from app.models.custo_infraestrutura import ComponenteInfra, CustoDiretoInfra
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

CENTAVO = Decimal("0.01")
CAMPOS_COMPONENTE = (
    "fornecedor", "servico", "categoria", "plano", "plano_referencia", "ciclo_cobranca", "moeda", "custo_contratado",
    "custo_referencia", "custo_real", "capacidade_contratada", "uso_atual", "unidade_uso", "politica_custo", "metodo_alocacao",
    "contabilizacao", "vigente_de", "vigente_ate", "observacoes",
)


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, ROUND_HALF_UP)


def _f(valor) -> float | None:
    return float(valor) if valor is not None else None


def competencia(dia: date) -> str:
    return dia.strftime("%Y-%m")


def vigentes(db: Session, dia: date) -> list[ComponenteInfra]:
    return (db.query(ComponenteInfra).filter(ComponenteInfra.vigente_de <= dia,
                                             or_(ComponenteInfra.vigente_ate.is_(None), ComponenteInfra.vigente_ate > dia))
            .order_by(ComponenteInfra.id).all())


def _em_brl(db: Session, valor: Decimal | None, moeda: str, dia: date) -> tuple[Decimal | None, dict | None, str | None]:
    """(valor em reais, snapshot da cotação, faltante). Moeda estrangeira usa a cotação PTAX aplicável ao dia."""
    if valor is None:
        return None, None, None
    if moeda == "BRL":
        return Decimal(str(valor)), None, None
    cotacao = finops.cambio.aplicavel(db, moeda, "BRL", datetime.combine(dia, datetime.max.time()))
    if cotacao is None:
        return None, None, Faltante.CAMBIO.value
    return Decimal(str(valor)) * Decimal(str(cotacao.taxa)), finops.cambio.snapshot(cotacao), None


def custos_mensais(db: Session, componente: ComponenteInfra, dia: date) -> dict:
    """Custo provisionado e real do componente por mês, em reais. `None` = valor não informado (nunca estimado)."""
    meses = CICLOS_COBRANCA[componente.ciclo_cobranca]
    base_provisionada = (componente.custo_referencia if componente.custo_referencia is not None else componente.custo_contratado) \
        if componente.politica_custo == PoliticaCustoInfra.PLANO_MAXIMO.value else componente.custo_real
    provisionado, fx, falta_fx = _em_brl(db, base_provisionada, componente.moeda, dia)
    real, fx_real, falta_fx_real = _em_brl(db, componente.custo_real, componente.moeda, dia)
    return {"provisionado": _q(provisionado / meses) if provisionado is not None else None,
            "real": _q(real / meses) if real is not None else None, "fx": fx or fx_real,
            "faltante": falta_fx or (None if base_provisionada is not None else Faltante.CUSTO_INFRA.value),
            "faltante_real": falta_fx_real}


def _diretos(db: Session, componente: ComponenteInfra, mes: str, dia: date) -> tuple[dict[str, Decimal] | None, str | None]:
    linhas = db.query(CustoDiretoInfra.tenant_id, func.sum(CustoDiretoInfra.custo)).filter_by(
        componente_id=componente.id, competencia=mes).group_by(CustoDiretoInfra.tenant_id).all()
    por_tenant = {}
    for tenant_id, custo in linhas:
        valor, _, falta = _em_brl(db, custo, componente.moeda, dia)
        if falta:
            return None, falta
        por_tenant[tenant_id] = _q(valor)
    return por_tenant, None


def unidades_ponderadas(db: Session, pesos: dict) -> tuple[Decimal, dict[str, Decimal], list[str]]:
    """(total de unidades, peso de cada tenant ativo, planos ativos sem tier/peso)."""
    linhas = (db.query(Tenant.id, Plano.nome, Plano.tier_infraestrutura).join(Licenca, Licenca.tenant_id == Tenant.id)
              .join(Plano, Plano.id == Licenca.plano_id).filter(Tenant.ativo.is_(True), Licenca.status == "ativa").all())
    por_tenant, sem_peso = {}, set()
    for tenant_id, plano, tier in linhas:
        if tier in pesos:
            por_tenant[tenant_id] = Decimal(str(pesos[tier]))
        else:
            sem_peso.add(plano)
    return sum(por_tenant.values(), Decimal(0)), por_tenant, sorted(sem_peso)


def pool(db: Session, dia: date) -> dict:
    """Pool do mês de `dia`: provisionado e real (reais/mês), unidades ponderadas e custos diretos por tenant."""
    regras = politica.vigente_infra(db).regras
    mes = competencia(dia)
    faltantes, componentes, diretos = [], [], {}
    pool_prov, pool_real, real_conhecido = Decimal(0), Decimal(0), True
    for componente in vigentes(db, dia):
        if componente.contabilizacao == Contabilizacao.CUSTO_IA.value:
            continue  # já está no custo de IA do FinOps
        custos = custos_mensais(db, componente, dia)
        linha = {"id": componente.id, "fornecedor": componente.fornecedor, "servico": componente.servico, "plano": componente.plano,
                 "plano_referencia": componente.plano_referencia, "metodo": componente.metodo_alocacao,
                 "provisionado": _f(custos["provisionado"]), "real": _f(custos["real"]), "fx": custos["fx"]}
        if custos["faltante"]:
            faltantes.append(custos["faltante"])
        prov, real = custos["provisionado"] or Decimal(0), custos["real"]
        if componente.metodo_alocacao == MetodoAlocacao.DIRETA.value:
            por_tenant, falta = _diretos(db, componente, mes, dia)
            if falta:
                faltantes.append(falta)
                por_tenant = {}
            medido = sum(por_tenant.values(), Decimal(0))
            for tenant_id, valor in por_tenant.items():
                diretos[tenant_id] = diretos.get(tenant_id, Decimal(0)) + valor
            prov, real = max(prov - medido, Decimal(0)), (max(real - medido, Decimal(0)) if real is not None else None)
            linha["direto_medido"] = float(medido)
        pool_prov += prov
        if real is None:
            real_conhecido = False
        else:
            pool_real += real
        componentes.append(linha)
    if not componentes:
        faltantes.append(Faltante.CUSTO_INFRA.value)
    unidades, pesos_tenant, sem_peso = unidades_ponderadas(db, regras["pesos"])
    return {"competencia": mes, "provisionado": _q(pool_prov), "real": _q(pool_real) if real_conhecido and componentes else None,
            "unidades": unidades, "pesos": pesos_tenant, "planos_sem_peso": sem_peso, "diretos": diretos, "componentes": componentes,
            "faltantes": sorted(set(faltantes)), "politica": regras}


def custo_tenant_mensal(dados: dict, tenant_id: str) -> tuple[Decimal | None, Decimal | None]:
    """(provisionado, real) por mês do tenant pela alocação ponderada, sem os custos diretos."""
    peso = dados["pesos"].get(tenant_id)
    if peso is None or not dados["unidades"]:
        return None, None
    prov = _q(dados["provisionado"] / dados["unidades"] * peso)
    real = _q(dados["real"] / dados["unidades"] * peso) if dados["real"] is not None else None
    return prov, real


def _diretos_nao_atribuidos(db: Session, apuracao: ApuracaoComissao) -> tuple[Decimal, str | None, str | None]:
    """Custos diretos medidos do tenant ainda não atribuídos a outro recebimento (marca d'água por competência)."""
    mes = competencia(apuracao.recebido_em)
    ultimo = db.query(func.max(ApuracaoComissao.custo_direto_ate)).filter(
        ApuracaoComissao.tenant_id == apuracao.tenant_id, ApuracaoComissao.id != apuracao.id).scalar()
    consulta = db.query(CustoDiretoInfra).filter(CustoDiretoInfra.tenant_id == apuracao.tenant_id, CustoDiretoInfra.competencia <= mes)
    if ultimo:
        consulta = consulta.filter(CustoDiretoInfra.competencia > ultimo)
    total = Decimal(0)
    for linha in consulta.all():
        componente = db.get(ComponenteInfra, linha.componente_id)
        if componente.contabilizacao == Contabilizacao.CUSTO_IA.value:
            continue
        valor, _, falta = _em_brl(db, linha.custo, componente.moeda, apuracao.recebido_em)
        if falta:
            return Decimal(0), None, falta
        total += valor
    return _q(total), mes, None


def alocar(db: Session, apuracao: ApuracaoComissao) -> tuple[Decimal | None, Decimal | None, dict]:
    """(custo provisionado, custo real, detalhe) atribuíveis ao recebimento. Provisionado None = aguarda (o detalhe traz
    `faltante`: INFRASTRUCTURE_COST ou FX_RATE). Real None = custo real ainda não informado (não bloqueia a comissão)."""
    dados = pool(db, apuracao.recebido_em)
    meses = Decimal(str(apuracao.meses_infra or 0))
    detalhe = {"competencia": dados["competencia"], "politica": dados["politica"], "pool_provisionado": float(dados["provisionado"]),
               "pool_real": _f(dados["real"]), "unidades_ponderadas": float(dados["unidades"]), "componentes": dados["componentes"],
               "meses": float(meses)}
    if dados["faltantes"]:
        return None, None, {**detalhe, "faltante": dados["faltantes"][0], "faltantes": dados["faltantes"]}
    peso = dados["pesos"].get(apuracao.tenant_id)
    if peso is None and meses:
        return None, None, {**detalhe, "faltante": Faltante.CUSTO_INFRA.value, "planos_sem_peso": dados["planos_sem_peso"]}
    prov_mes, real_mes = custo_tenant_mensal(dados, apuracao.tenant_id) if meses else (Decimal(0), Decimal(0))
    direto, ate, falta = _diretos_nao_atribuidos(db, apuracao) if meses else (Decimal(0), None, None)
    if falta:
        return None, None, {**detalhe, "faltante": falta}
    apuracao.custo_direto_ate = ate
    prov = _q(prov_mes * meses + direto)
    real = _q(real_mes * meses + direto) if real_mes is not None else None
    return prov, real, {**detalhe, "peso_tenant": _f(peso), "custo_mensal_provisionado": _f(prov_mes), "custo_mensal_real": _f(real_mes),
                        "custo_unidade": _f(_q(dados["provisionado"] / dados["unidades"])) if dados["unidades"] else None,
                        "direto": float(direto)}


def custo_ia_brl(db: Session, tenant_id: str, inicio: datetime, fim: datetime) -> tuple[Decimal | None, str | None]:
    """(custo real de IA do tenant no intervalo, motivo se desconhecido). Execução sem custo em reais é convertida pela
    PTAX aplicável ao instante dela; sem cotação → FX_RATE; modelo sem preço → INFRASTRUCTURE_COST."""
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
    return _q(total), None


def custo_ia(db: Session, apuracao: ApuracaoComissao, janela_dias: int = 30) -> tuple[Decimal | None, str | None]:
    """Custo de IA ainda não atribuído do tenant até o recebimento (marca d'água `custo_ia_ate`): parcelas não repetem o
    mesmo custo. Calculado sempre (MAP/FinOps); só entra na comissão se a política da margem mandar."""
    fim = datetime.combine(apuracao.recebido_em + timedelta(days=1), datetime.min.time())
    ultimo = db.query(func.max(ApuracaoComissao.custo_ia_ate)).filter(
        ApuracaoComissao.tenant_id == apuracao.tenant_id, ApuracaoComissao.id != apuracao.id,
        ApuracaoComissao.custo_ia_ate.isnot(None)).scalar()
    inicio = ultimo or fim - timedelta(days=janela_dias)
    valor, motivo = custo_ia_brl(db, apuracao.tenant_id, inicio, fim) if fim > inicio else (Decimal(0), None)
    apuracao.custo_ia = valor
    apuracao.custo_ia_ate = fim if valor is not None else None
    return valor, motivo


# ---------------------------------------------------------------- cadastro (Admin → Parâmetros financeiros → Infraestrutura)


def _validar(dados: dict) -> None:
    if not (dados.get("fornecedor") or "").strip() or not (dados.get("servico") or "").strip():
        raise ValidacaoFalhou("Informe fornecedor e serviço.")
    if dados.get("categoria") not in CATEGORIAS_INFRA:
        raise ValidacaoFalhou(f"Categoria: {', '.join(CATEGORIAS_INFRA)}.")
    if dados.get("ciclo_cobranca") not in CICLOS_COBRANCA:
        raise ValidacaoFalhou(f"Ciclo de cobrança: {', '.join(CICLOS_COBRANCA)}.")
    if len(dados.get("moeda") or "") != 3:
        raise ValidacaoFalhou("Moeda com 3 letras (ex.: BRL, USD).")
    if dados.get("politica_custo") not in {p.value for p in PoliticaCustoInfra}:
        raise ValidacaoFalhou("Política de custo: MAX_CONTRACTED_PLAN ou ACTUAL_COST.")
    if dados.get("metodo_alocacao") not in {m.value for m in MetodoAlocacao}:
        raise ValidacaoFalhou("Alocação: WEIGHTED ou DIRECT.")
    if dados.get("contabilizacao") not in {c.value for c in Contabilizacao}:
        raise ValidacaoFalhou("Contabilização: INFRASTRUCTURE ou AI_COST.")
    if dados["categoria"] == "AI" and dados["contabilizacao"] != Contabilizacao.CUSTO_IA.value:
        raise ValidacaoFalhou("Custo de IA é contabilizado como AI_COST (FinOps), nunca de novo como infraestrutura.")
    for campo in ("custo_contratado", "custo_referencia", "custo_real", "capacidade_contratada", "uso_atual"):
        if dados.get(campo) is not None and Decimal(str(dados[campo])) < 0:
            raise ValidacaoFalhou(f"{campo} não pode ser negativo.")
    if dados.get("vigente_ate") is not None and dados["vigente_ate"] <= dados["vigente_de"]:
        raise ValidacaoFalhou("O fim da vigência precisa ser depois do início.")


def _foto(componente: ComponenteInfra) -> dict:
    return {c: (str(v) if isinstance(v, Decimal | date) else v) for c in CAMPOS_COMPONENTE for v in [getattr(componente, c)]}


def criar(db: Session, dados: dict, ator_id: str | None) -> ComponenteInfra:
    dados = {**dados, "moeda": (dados.get("moeda") or "").upper()}
    _validar(dados)
    componente = ComponenteInfra(**{c: dados.get(c) for c in CAMPOS_COMPONENTE}, criado_por=ator_id)
    db.add(componente)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "componente_infra_criado", "componente_infra", componente.id,
                                ator_id, {"depois": _foto(componente), "origem": "admin"})
    return componente


def atualizar(db: Session, componente_id: int, dados: dict, motivo: str, ator_id: str | None) -> ComponenteInfra:
    """Mudança de plano, custo, capacidade ou alocação: auditada (antes/depois). Comissões já calculadas guardam o snapshot."""
    if not (motivo or "").strip():
        raise ValidacaoFalhou("Informe o motivo da alteração.")
    componente = db.get(ComponenteInfra, componente_id)
    if componente is None:
        raise NaoEncontrado(f"Componente {componente_id} não encontrado")
    antes = _foto(componente)
    novos = {**{c: getattr(componente, c) for c in CAMPOS_COMPONENTE}, **{c: v for c, v in dados.items() if c in CAMPOS_COMPONENTE}}
    novos["moeda"] = (novos.get("moeda") or "").upper()
    _validar(novos)
    numericos = ("custo_contratado", "custo_referencia", "custo_real", "capacidade_contratada", "uso_atual")
    for campo, valor in novos.items():
        setattr(componente, campo, Decimal(str(valor)) if campo in numericos and valor is not None else valor)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "componente_infra_alterado", "componente_infra", componente.id,
                                ator_id, {"antes": antes, "depois": _foto(componente), "motivo": motivo, "origem": "admin"})
    return componente


def registrar_custo_direto(db: Session, dados: dict, ator_id: str | None) -> CustoDiretoInfra:
    componente = db.get(ComponenteInfra, dados.get("componente_id"))
    if componente is None:
        raise NaoEncontrado("Componente não encontrado")
    if componente.metodo_alocacao != MetodoAlocacao.DIRETA.value:
        raise ValidacaoFalhou("Custo direto só em componente com alocação DIRECT.")
    if db.get(Tenant, dados.get("tenant_id")) is None:
        raise NaoEncontrado("Tenant não encontrado")
    competencia_ = dados.get("competencia") or ""
    if len(competencia_) != 7 or competencia_[4] != "-":
        raise ValidacaoFalhou("Competência no formato AAAA-MM.")
    if dados.get("custo") is None or Decimal(str(dados["custo"])) < 0:
        raise ValidacaoFalhou("Custo direto não negativo.")
    linha = CustoDiretoInfra(componente_id=componente.id, tenant_id=dados["tenant_id"], competencia=competencia_,
                             quantidade=dados.get("quantidade"), custo=Decimal(str(dados["custo"])), fonte=dados.get("fonte"),
                             criado_por=ator_id)
    db.add(linha)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "custo_direto_infra_registrado", "custo_direto_infra", linha.id,
                                ator_id, {"componente_id": componente.id, "tenant_id": linha.tenant_id, "competencia": competencia_,
                                          "custo": str(linha.custo), "moeda": componente.moeda, "origem": "admin"})
    return linha


def como_dict(componente: ComponenteInfra) -> dict:
    return {"id": componente.id, **{c: (_f(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, date) else v)
                                    for c in CAMPOS_COMPONENTE for v in [getattr(componente, c)]}}
