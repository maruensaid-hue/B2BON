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

D-077: só entram no pool os componentes vigentes, APLICÁVEIS à arquitetura real e provisionados para comissão, dos pools
que a política inclui (INFRASTRUCTURE e DATA_PROVIDER). Para o mesmo fornecedor/serviço vale a fonte de maior prioridade
(fatura/contrato > proposta > preço público). Preço por uso (ex.: Neon) só tem custo provisionado com Capacity Envelope;
preço CUSTOM nunca recebe valor inventado. Com capacidade compartilhada configurada, a parte do pool não absorvida pela
base fica como UNALLOCATED_INFRASTRUCTURE_CAPACITY (custo de capacidade ociosa da plataforma), separada da alocação.

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
    PRIORIDADE_FONTE,
    STATUS_NO_POOL,
    Contabilizacao,
    Faltante,
    MetodoAlocacao,
    ModeloPreco,
    PoliticaCustoInfra,
    StatusArquitetura,
    TipoFonte,
)
from app.contexts.finops import contract as finops
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.creditos_ia import ExecucaoIa
from app.models.custo_infraestrutura import ComponenteInfra, CustoDiretoInfra, EnvelopeCapacidade
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

CENTAVO = Decimal("0.01")
CAMPOS_COMPONENTE = (
    "fornecedor", "servico", "categoria", "plano", "plano_referencia", "ciclo_cobranca", "moeda", "custo_contratado",
    "custo_referencia", "custo_real", "capacidade_contratada", "uso_atual", "unidade_uso", "politica_custo", "metodo_alocacao",
    "contabilizacao", "vigente_de", "vigente_ate", "observacoes", "modelo_preco", "status_arquitetura", "provisionado_para_comissao",
    "funcao_arquitetural", "coexistencia_justificada", "url_fonte", "tipo_fonte", "verificado_em", "proxima_revisao_em",
    "override_manual", "motivo_override", "atributos",
)
PADROES = {"modelo_preco": ModeloPreco.PLANO_FIXO.value, "status_arquitetura": StatusArquitetura.APLICAVEL.value,
           "provisionado_para_comissao": True, "tipo_fonte": TipoFonte.MANUAL.value, "override_manual": False}


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


def aplicaveis(db: Session, dia: date, pools: list[str]) -> list[ComponenteInfra]:
    """Componentes do pool da comissão: vigentes, aplicáveis à arquitetura, provisionados e dos pools da política. Para o
    mesmo fornecedor/serviço fica a fonte de maior prioridade (a outra é substituída, nunca somada)."""
    escolhidos: dict[tuple, ComponenteInfra] = {}
    for componente in vigentes(db, dia):
        if componente.status_arquitetura not in STATUS_NO_POOL or not componente.provisionado_para_comissao \
                or componente.contabilizacao not in pools:
            continue
        chave = (componente.fornecedor.strip().lower(), componente.servico.strip().lower())
        atual = escolhidos.get(chave)
        if atual is None or (PRIORIDADE_FONTE.get(componente.tipo_fonte, 0), componente.vigente_de, componente.id) > \
                (PRIORIDADE_FONTE.get(atual.tipo_fonte, 0), atual.vigente_de, atual.id):
            escolhidos[chave] = componente
    return sorted(escolhidos.values(), key=lambda c: c.id)


def envelope_vigente(db: Session, componente: ComponenteInfra, dia: date) -> EnvelopeCapacidade | None:
    """Capacity Envelope em vigor (nunca um benchmark do fornecedor)."""
    return (db.query(EnvelopeCapacidade).filter(
        EnvelopeCapacidade.componente_id == componente.id, EnvelopeCapacidade.benchmark_only.is_(False),
        EnvelopeCapacidade.vigente_de <= dia, or_(EnvelopeCapacidade.vigente_ate.is_(None), EnvelopeCapacidade.vigente_ate > dia))
        .order_by(EnvelopeCapacidade.vigente_de.desc(), EnvelopeCapacidade.id.desc()).first())


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
    envelope = None
    if componente.politica_custo == PoliticaCustoInfra.CUSTO_REAL.value:
        base_provisionada = componente.custo_real
    elif componente.modelo_preco == ModeloPreco.USO.value:
        envelope = envelope_vigente(db, componente, dia)  # preço por uso: provisionado = envelope decidido pela CyberFort
        base_provisionada, meses = (envelope.custo_mensal_estimado, 1) if envelope else (None, meses)
    else:  # plano fixo (referência ou atual); CUSTOM só com valor de contrato/proposta, nunca inventado
        base_provisionada = componente.custo_referencia if componente.custo_referencia is not None else componente.custo_contratado
    provisionado, fx, falta_fx = _em_brl(db, base_provisionada, componente.moeda, dia)
    real, fx_real, falta_fx_real = _em_brl(db, componente.custo_real, componente.moeda, dia)
    return {"provisionado": _q(provisionado / meses) if provisionado is not None else None,
            "real": _q(real / meses) if real is not None else None, "fx": fx or fx_real,
            "faltante": falta_fx or (None if base_provisionada is not None else Faltante.CUSTO_INFRA.value),
            "faltante_real": falta_fx_real, "envelope_id": envelope.id if envelope else None}


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
    por_pool: dict[str, Decimal] = {}
    for componente in aplicaveis(db, dia, regras.get("pools_comissao") or ["INFRASTRUCTURE", "DATA_PROVIDER"]):
        custos = custos_mensais(db, componente, dia)
        linha = {"id": componente.id, "fornecedor": componente.fornecedor, "servico": componente.servico, "plano": componente.plano,
                 "plano_referencia": componente.plano_referencia, "metodo": componente.metodo_alocacao,
                 "pool": componente.contabilizacao, "modelo_preco": componente.modelo_preco, "tipo_fonte": componente.tipo_fonte,
                 "verificado_em": componente.verificado_em.isoformat() if componente.verificado_em else None,
                 "envelope_id": custos["envelope_id"], "provisionado": _f(custos["provisionado"]), "real": _f(custos["real"]),
                 "fx": custos["fx"]}
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
        por_pool[componente.contabilizacao] = por_pool.get(componente.contabilizacao, Decimal(0)) + prov
        if real is None:
            real_conhecido = False
        else:
            pool_real += real
        componentes.append(linha)
    if not componentes:
        faltantes.append(Faltante.CUSTO_INFRA.value)
    unidades, pesos_tenant, sem_peso = unidades_ponderadas(db, regras["pesos"])
    capacidade = Decimal(str(regras["capacidade_unidades"])) if regras.get("capacidade_unidades") else Decimal(0)
    divisor = max(unidades, capacidade)  # sem tenants: nada é dividido (nunca divisão por zero)
    alocado = _q(pool_prov / divisor * unidades) if divisor else Decimal(0)
    return {"competencia": mes, "provisionado": _q(pool_prov), "real": _q(pool_real) if real_conhecido and componentes else None,
            "por_pool": {k: float(_q(v)) for k, v in sorted(por_pool.items())}, "unidades": unidades, "divisor": divisor,
            "alocado_tenants": alocado, "capacidade_nao_alocada": _q(pool_prov - alocado), "pesos": pesos_tenant,
            "planos_sem_peso": sem_peso, "diretos": diretos, "componentes": componentes, "faltantes": sorted(set(faltantes)),
            "politica": regras}


def custo_tenant_mensal(dados: dict, tenant_id: str) -> tuple[Decimal | None, Decimal | None]:
    """(provisionado, real) por mês do tenant pela alocação ponderada, sem os custos diretos."""
    peso = dados["pesos"].get(tenant_id)
    if peso is None or not dados["divisor"]:
        return None, None
    prov = _q(dados["provisionado"] / dados["divisor"] * peso)
    real = _q(dados["real"] / dados["divisor"] * peso) if dados["real"] is not None else None
    return prov, real


def _diretos_nao_atribuidos(db: Session, apuracao: ApuracaoComissao) -> tuple[Decimal, str | None, str | None]:
    """Custos diretos medidos do tenant ainda não atribuídos a outro recebimento (marca d'água por competência)."""
    mes = competencia(apuracao.recebido_em)
    ultimo = db.query(func.max(ApuracaoComissao.custo_direto_ate)).filter(
        ApuracaoComissao.tenant_id == apuracao.tenant_id, ApuracaoComissao.id != apuracao.id).scalar()
    consulta = db.query(CustoDiretoInfra).filter(CustoDiretoInfra.tenant_id == apuracao.tenant_id, CustoDiretoInfra.competencia <= mes)
    if ultimo:
        consulta = consulta.filter(CustoDiretoInfra.competencia > ultimo)
    pools = politica.vigente_infra(db).regras.get("pools_comissao") or ["INFRASTRUCTURE", "DATA_PROVIDER"]
    total = Decimal(0)
    for linha in consulta.all():
        componente = db.get(ComponenteInfra, linha.componente_id)
        if componente.contabilizacao not in pools or componente.status_arquitetura not in STATUS_NO_POOL:
            continue  # custo de IA/dados do FinOps ou componente fora da arquitetura: nunca de novo aqui
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
               "pool_real": _f(dados["real"]), "por_pool": dados["por_pool"], "unidades_ponderadas": float(dados["unidades"]),
               "divisor": float(dados["divisor"]), "capacidade_nao_alocada": float(dados["capacidade_nao_alocada"]),
               "componentes": dados["componentes"], "meses": float(meses)}
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
                        "custo_unidade": _f(_q(dados["provisionado"] / dados["divisor"])) if dados["divisor"] else None,
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
    if dados.get("modelo_preco") not in {m.value for m in ModeloPreco}:
        raise ValidacaoFalhou("Modelo de preço: FIXED_PLAN, USAGE_BASED ou CUSTOM.")
    if dados.get("status_arquitetura") not in {s.value for s in StatusArquitetura}:
        raise ValidacaoFalhou("Status: APPLICABLE, APPLICABLE_PENDING_CONFIRMATION ou AVAILABLE_NOT_ALLOCATED.")
    if dados.get("tipo_fonte") not in {t.value for t in TipoFonte}:
        raise ValidacaoFalhou(f"Fonte do preço: {', '.join(t.value for t in TipoFonte)}.")
    if dados["modelo_preco"] == ModeloPreco.CUSTOM.value and dados.get("tipo_fonte") == TipoFonte.PUBLICO.value \
            and (dados.get("custo_referencia") is not None or dados.get("custo_contratado") is not None):
        raise ValidacaoFalhou("Plano CUSTOM não tem preço público: valor só com contrato, proposta ou fatura.")
    if dados.get("override_manual") and not (dados.get("motivo_override") or "").strip():
        raise ValidacaoFalhou("Override manual exige motivo.")
    for campo in ("custo_contratado", "custo_referencia", "custo_real", "capacidade_contratada", "uso_atual"):
        if dados.get(campo) is not None and Decimal(str(dados[campo])) < 0:
            raise ValidacaoFalhou(f"{campo} não pode ser negativo.")
    if dados.get("vigente_ate") is not None and dados["vigente_ate"] <= dados["vigente_de"]:
        raise ValidacaoFalhou("O fim da vigência precisa ser depois do início.")


def _foto(componente: ComponenteInfra) -> dict:
    return {c: (str(v) if isinstance(v, Decimal | date) else v) for c in CAMPOS_COMPONENTE for v in [getattr(componente, c)]}


def _sem_dupla_contagem(db: Session, dados: dict, componente_id: int | None = None) -> None:
    """Uma despesa não entra duas vezes: (1) o mesmo fornecedor/serviço/plano/fonte com vigência sobreposta; (2) dois
    componentes aplicáveis na mesma função arquitetural (ex.: Neon e Render Postgres como banco principal) sem a
    coexistência justificada. Pools diferentes para a mesma despesa são impossíveis: cada componente tem um pool só."""
    if dados.get("status_arquitetura") not in STATUS_NO_POOL or not dados.get("provisionado_para_comissao"):
        return
    inicio, fim = dados["vigente_de"], dados.get("vigente_ate") or date.max
    for outro in db.query(ComponenteInfra).filter(ComponenteInfra.id != (componente_id or 0)).all():
        if outro.status_arquitetura not in STATUS_NO_POOL or not outro.provisionado_para_comissao:
            continue
        if not (outro.vigente_de < fim and inicio < (outro.vigente_ate or date.max)):
            continue
        mesmo = (outro.fornecedor.strip().lower(), outro.servico.strip().lower(), (outro.plano or "").lower(), outro.tipo_fonte) == (
            dados["fornecedor"].strip().lower(), dados["servico"].strip().lower(), (dados.get("plano") or "").lower(), dados["tipo_fonte"])
        if mesmo:
            raise ValidacaoFalhou(f"{outro.fornecedor} · {outro.servico} já está no pool nessa vigência (dupla contagem).")
        funcao = dados.get("funcao_arquitetural")
        if funcao and outro.funcao_arquitetural == funcao and not (dados.get("coexistencia_justificada") or "").strip() \
                and (outro.fornecedor.strip().lower(), outro.servico.strip().lower()) != (dados["fornecedor"].strip().lower(),
                                                                                         dados["servico"].strip().lower()):
            raise ValidacaoFalhou(f"{outro.fornecedor} · {outro.servico} já ocupa a função {funcao}; os dois só entram juntos com a "
                                  "coexistência justificada (uso real dos dois).")


def criar(db: Session, dados: dict, ator_id: str | None) -> ComponenteInfra:
    dados = {**PADROES, **{k: v for k, v in dados.items() if v is not None or k not in PADROES}, "moeda": (dados.get("moeda") or "").upper()}
    _validar(dados)
    _sem_dupla_contagem(db, dados)
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
    _sem_dupla_contagem(db, novos, componente.id)
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


def criar_envelope(db: Session, componente_id: int, dados: dict, ator_id: str | None) -> EnvelopeCapacidade:
    """Capacity Envelope de um componente por uso: as quantidades são decisão da CyberFort (nunca inventadas). Preços
    unitários vêm do envelope ou dos atributos do componente (preço público verificado)."""
    componente = db.get(ComponenteInfra, componente_id)
    if componente is None:
        raise NaoEncontrado("Componente não encontrado")
    if componente.modelo_preco != ModeloPreco.USO.value:
        raise ValidacaoFalhou("Capacity Envelope só para componente com preço por uso (USAGE_BASED).")
    unitarios = (componente.atributos or {}).get("precos_unitarios") or {}
    preco_cu = dados.get("preco_unidade_computo", unitarios.get("CU_HOUR"))
    preco_gb = dados.get("preco_armazenamento_gb", unitarios.get("GB_MONTH"))
    horas, gb = dados.get("horas_computo_provisionadas"), dados.get("armazenamento_gb_provisionado")
    outros = dados.get("outros_custos") or []
    if any(v is not None and Decimal(str(v)) < 0 for v in (horas, gb, preco_cu, preco_gb, dados.get("max_unidades_computo"))):
        raise ValidacaoFalhou("Quantidades e preços não negativos.")
    benchmark = bool(dados.get("benchmark_only"))
    if benchmark:
        estimado = dados.get("custo_mensal_estimado")
    else:
        if horas is None or gb is None:
            raise ValidacaoFalhou("Informe as horas de computação e o armazenamento provisionados (decisão da CyberFort).")
        if (Decimal(str(horas)) and preco_cu is None) or (Decimal(str(gb)) and preco_gb is None):
            raise ValidacaoFalhou("Preço unitário de computação/armazenamento não informado.")
        estimado = Decimal(str(horas)) * Decimal(str(preco_cu or 0)) + Decimal(str(gb)) * Decimal(str(preco_gb or 0)) \
            + sum((Decimal(str(o["valor"])) for o in outros), Decimal(0))
    envelope = EnvelopeCapacidade(
        componente_id=componente.id, max_unidades_computo=dados.get("max_unidades_computo"), horas_computo_provisionadas=horas,
        armazenamento_gb_provisionado=gb, preco_unidade_computo=preco_cu, preco_armazenamento_gb=preco_gb, outros_custos=outros or None,
        custo_mensal_estimado=_q(Decimal(str(estimado))) if estimado is not None else None, moeda=componente.moeda,
        vigente_de=dados.get("vigente_de") or date.today(), vigente_ate=dados.get("vigente_ate"), fonte=dados.get("fonte"),
        verificado_em=dados.get("verificado_em"), benchmark_only=benchmark, observacoes=dados.get("observacoes"), criado_por=ator_id)
    db.add(envelope)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "envelope_capacidade_criado", "envelope_capacidade", envelope.id,
                                ator_id, {"componente_id": componente.id, "custo_mensal_estimado": str(envelope.custo_mensal_estimado),
                                          "benchmark_only": benchmark, "origem": "admin"})
    return envelope


def envelope_dict(envelope: EnvelopeCapacidade) -> dict:
    return {"id": envelope.id, "componente_id": envelope.componente_id, "max_unidades_computo": _f(envelope.max_unidades_computo),
            "horas_computo_provisionadas": _f(envelope.horas_computo_provisionadas),
            "armazenamento_gb_provisionado": _f(envelope.armazenamento_gb_provisionado),
            "preco_unidade_computo": _f(envelope.preco_unidade_computo), "preco_armazenamento_gb": _f(envelope.preco_armazenamento_gb),
            "custo_mensal_estimado": _f(envelope.custo_mensal_estimado), "moeda": envelope.moeda, "benchmark_only": envelope.benchmark_only,
            "vigente_de": envelope.vigente_de.isoformat(), "fonte": envelope.fonte, "observacoes": envelope.observacoes}


def como_dict(componente: ComponenteInfra) -> dict:
    return {"id": componente.id, **{c: (_f(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, date) else v)
                                    for c in CAMPOS_COMPONENTE for v in [getattr(componente, c)]}}
