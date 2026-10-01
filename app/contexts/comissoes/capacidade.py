"""Capacidade e economia dos fornecedores de infraestrutura (D-076).

- Status por utilização (uso ÷ capacidade contratada) com limiares da política de infraestrutura: NORMAL < 70%,
  ATTENTION ≥ 70%, REVIEW ≥ 80%, CRITICAL ≥ 90%, CAPACITY_REACHED ≥ 100% (configuráveis).
- Ao cruzar REVIEW, CRITICAL ou CAPACITY_REACHED nasce um alerta com a recomendação. Nada é contratado ou alterado sozinho:
  o alerta só fecha com a decisão registrada por uma pessoa.
- Projeção determinística (regressão linear do uso medido; tendência de tenants ativos), sem LLM.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.comissoes import infraestrutura, politica
from app.contexts.comissoes.tipos import MENSAGENS_CAPACIDADE, StatusCapacidade
from app.models.custo_infraestrutura import AlertaCapacidadeInfra, ComponenteInfra, UsoCapacidadeInfra
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services import auditoria_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

ORDEM = (StatusCapacidade.NORMAL, StatusCapacidade.ATENCAO, StatusCapacidade.REVISAR, StatusCapacidade.CRITICO, StatusCapacidade.ESGOTADA)
HORIZONTES_DIAS = (30, 90, 180)


def _agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def utilizacao(componente: ComponenteInfra) -> float | None:
    if not componente.capacidade_contratada or componente.uso_atual is None:
        return None
    return float(Decimal(str(componente.uso_atual)) / Decimal(str(componente.capacidade_contratada)))


def status(uso_relativo: float | None, limiares: dict) -> str | None:
    if uso_relativo is None:
        return None
    atual = StatusCapacidade.NORMAL.value
    for nivel in ORDEM[1:]:
        if uso_relativo >= float(limiares[nivel.value]):
            atual = nivel.value
    return atual


def registrar_uso(db: Session, componente_id: int, uso, ator_id: str | None, fonte: str | None = None,
                  medido_em: datetime | None = None) -> dict:
    """Uso medido: histórico, status e alerta (sem nenhuma ação automática sobre plano ou fornecedor)."""
    componente = db.get(ComponenteInfra, componente_id)
    if componente is None:
        raise NaoEncontrado(f"Componente {componente_id} não encontrado")
    if uso is None or Decimal(str(uso)) < 0:
        raise ValidacaoFalhou("Uso medido não negativo.")
    limiares = politica.vigente_infra(db).regras["limiares"]
    antes = status(utilizacao(componente), limiares)
    componente.uso_atual = Decimal(str(uso))
    db.add(UsoCapacidadeInfra(componente_id=componente.id, medido_em=medido_em or _agora(), uso=Decimal(str(uso)), fonte=fonte,
                              registrado_por=ator_id))
    depois = status(utilizacao(componente), limiares)
    alerta = None
    if depois in MENSAGENS_CAPACIDADE and ORDEM.index(StatusCapacidade(depois)) > ORDEM.index(StatusCapacidade(antes or "NORMAL")):
        alerta = AlertaCapacidadeInfra(componente_id=componente.id, nivel=depois, utilizacao=round(utilizacao(componente), 4),
                                       mensagem=MENSAGENS_CAPACIDADE[depois], status="ABERTO")
        db.add(alerta)
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "uso_capacidade_infra_registrado", "componente_infra",
                                componente.id, ator_id, {"uso": str(uso), "status_antes": antes, "status_depois": depois,
                                                         "alerta": alerta.nivel if alerta else None, "origem": "admin"})
    return {"status": depois, "utilizacao": utilizacao(componente), "alerta": alerta_dict(alerta) if alerta else None}


def decidir_alerta(db: Session, alerta_id: int, decisao: str, ator_id: str | None) -> AlertaCapacidadeInfra:
    """Registro da decisão humana (upgrade, contrato Enterprise, desconto, parceria, manter). A plataforma não executa."""
    alerta = db.get(AlertaCapacidadeInfra, alerta_id)
    if alerta is None:
        raise NaoEncontrado("Alerta não encontrado")
    if not (decisao or "").strip():
        raise ValidacaoFalhou("Registre a decisão tomada.")
    alerta.status, alerta.decisao, alerta.decidido_por, alerta.decidido_em = "DECIDIDO", decisao.strip(), ator_id, _agora()
    db.flush()
    auditoria_service.registrar(db, auditoria_service.TENANT_PLATAFORMA, "alerta_capacidade_decidido", "alerta_capacidade_infra",
                                alerta.id, ator_id, {"nivel": alerta.nivel, "decisao": alerta.decisao, "origem": "admin"})
    return alerta


def alerta_dict(alerta: AlertaCapacidadeInfra) -> dict:
    return {"id": alerta.id, "componente_id": alerta.componente_id, "nivel": alerta.nivel, "utilizacao": alerta.utilizacao,
            "mensagem": alerta.mensagem, "status": alerta.status, "decisao": alerta.decisao,
            "criado_em": alerta.criado_em.isoformat() if alerta.criado_em else None}


def _tendencia(pontos: list[tuple[float, float]]) -> float | None:
    """Inclinação (por dia) da regressão linear de (dias, valor); None com menos de dois pontos distintos."""
    if len(pontos) < 2:
        return None
    media_x = sum(x for x, _ in pontos) / len(pontos)
    media_y = sum(y for _, y in pontos) / len(pontos)
    variancia = sum((x - media_x) ** 2 for x, _ in pontos)
    if variancia == 0:
        return None
    return sum((x - media_x) * (y - media_y) for x, y in pontos) / variancia


def projecao(db: Session, componente: ComponenteInfra) -> dict:
    """Utilização projetada (30/90/180 dias) e data estimada de esgotamento, pela tendência do uso medido."""
    historico = db.query(UsoCapacidadeInfra).filter_by(componente_id=componente.id).order_by(UsoCapacidadeInfra.medido_em).all()
    if not historico or not componente.capacidade_contratada:
        return {"inclinacao_dia": None, "utilizacao_projetada": {}, "esgotamento_estimado": None}
    origem = historico[0].medido_em
    pontos = [((h.medido_em - origem).total_seconds() / 86400, float(h.uso)) for h in historico]
    inclinacao = _tendencia(pontos)
    capacidade, ultimo_dia, ultimo_uso = float(componente.capacidade_contratada), pontos[-1][0], pontos[-1][1]
    if inclinacao is None:
        return {"inclinacao_dia": None, "utilizacao_projetada": {}, "esgotamento_estimado": None}
    projetada = {f"{d}d": round((ultimo_uso + inclinacao * d) / capacidade, 4) for d in HORIZONTES_DIAS}
    esgotamento = None
    if ultimo_uso >= capacidade:
        esgotamento = historico[-1].medido_em.date().isoformat()
    elif inclinacao > 0:
        dias = (capacidade - ultimo_uso) / inclinacao
        esgotamento = (origem + timedelta(days=ultimo_dia + dias)).date().isoformat()
    return {"inclinacao_dia": round(inclinacao, 6), "utilizacao_projetada": projetada, "esgotamento_estimado": esgotamento}


def receita_recorrente_mensal(db: Session) -> Decimal:
    """MRR dos tenants ativos: mensalidade dos planos privados + subscrição anual Government ÷ 12 (base de custo/receita)."""
    linhas = (db.query(Plano.preco_mensal, Plano.segmento, Plano.preco_assinatura_anual).join(Licenca, Licenca.plano_id == Plano.id)
              .join(Tenant, Tenant.id == Licenca.tenant_id).filter(Tenant.ativo.is_(True), Licenca.status == "ativa").all())
    total = Decimal(0)
    for preco_mensal, segmento, anual in linhas:
        total += Decimal(str(anual or 0)) / 12 if segmento == "GOVERNMENT" else Decimal(str(preco_mensal or 0))
    return total


def _tenants_projetados(db: Session, dias: int = 90) -> dict:
    """Tenants ativos hoje e projetados em `dias` pela tendência de criação dos últimos 180 dias."""
    hoje = _agora()
    ativos = db.query(func.count(Tenant.id)).filter(Tenant.ativo.is_(True)).scalar() or 0
    novos = db.query(func.count(Tenant.id)).filter(Tenant.ativo.is_(True), Tenant.criado_em >= hoje - timedelta(days=180)).scalar() or 0
    return {"ativos": ativos, "projetados": round(ativos + novos / 180 * dias, 1), "horizonte_dias": dias}


def economia_fornecedores(db: Session, dia: date | None = None) -> dict:
    """Provider Economics: plano atual × referência, custos, capacidade, uso, custos unitários, projeção e status."""
    dia = dia or _agora().date()
    regras = politica.vigente_infra(db).regras
    dados = infraestrutura.pool(db, dia)
    mrr = receita_recorrente_mensal(db)
    tenants = len(dados["pesos"])
    linhas, total_prov = [], Decimal(0)
    no_pool = {c.id for c in infraestrutura.aplicaveis(db, dia, regras.get("pools_comissao") or ["INFRASTRUCTURE", "DATA_PROVIDER"])}
    for componente in infraestrutura.vigentes(db, dia):
        custos = infraestrutura.custos_mensais(db, componente, dia)
        prov = custos["provisionado"]
        if prov is not None and componente.id in no_pool:
            total_prov += prov
        uso_relativo = utilizacao(componente)
        envelope = infraestrutura.envelope_vigente(db, componente, dia)
        linhas.append({
            "id": componente.id, "fornecedor": componente.fornecedor, "servico": componente.servico, "categoria": componente.categoria,
            "plano_atual": componente.plano, "plano_referencia": componente.plano_referencia, "moeda": componente.moeda,
            "custo_contratado": infraestrutura._f(componente.custo_contratado), "custo_referencia": infraestrutura._f(componente.custo_referencia),
            "custo_real": infraestrutura._f(componente.custo_real), "custo_provisionado_mensal_brl": infraestrutura._f(prov),
            "custo_real_mensal_brl": infraestrutura._f(custos["real"]), "contabilizacao": componente.contabilizacao,
            "capacidade": infraestrutura._f(componente.capacidade_contratada), "uso": infraestrutura._f(componente.uso_atual),
            "unidade_uso": componente.unidade_uso, "utilizacao": round(uso_relativo, 4) if uso_relativo is not None else None,
            "no_pool_comissao": componente.id in no_pool, "status_arquitetura": componente.status_arquitetura,
            "modelo_preco": componente.modelo_preco, "tipo_fonte": componente.tipo_fonte, "url_fonte": componente.url_fonte,
            "verificado_em": componente.verificado_em.isoformat() if componente.verificado_em else None,
            "proxima_revisao_em": componente.proxima_revisao_em.isoformat() if componente.proxima_revisao_em else None,
            "revisao_vencida": bool(componente.proxima_revisao_em and componente.proxima_revisao_em <= dia),
            "envelope": infraestrutura.envelope_dict(envelope) if envelope else None, "atributos": componente.atributos,
            "status": status(uso_relativo, regras["limiares"]),
            "custo_por_tenant": float(prov / tenants) if prov is not None and tenants else None,
            "custo_por_unidade_ponderada": float(prov / dados["divisor"]) if prov is not None and dados["divisor"] else None,
            "custo_sobre_receita": round(float(prov / mrr), 4) if prov is not None and mrr else None,
            "projecao": projecao(db, componente),
        })
    for linha in linhas:
        valor = linha["custo_provisionado_mensal_brl"]
        linha["participacao_pool"] = round(valor / float(total_prov), 4) if valor is not None and total_prov and \
            linha["no_pool_comissao"] else None
    por_fornecedor: dict[str, float] = {}
    for linha in linhas:
        if linha["participacao_pool"]:
            por_fornecedor[linha["fornecedor"]] = por_fornecedor.get(linha["fornecedor"], 0) + linha["participacao_pool"]
    maior = max(por_fornecedor.items(), key=lambda i: i[1]) if por_fornecedor else None
    alertas = db.query(AlertaCapacidadeInfra).filter_by(status="ABERTO").order_by(AlertaCapacidadeInfra.id.desc()).all()
    tenants_proj = _tenants_projetados(db)
    fator = Decimal(str(tenants_proj["projetados"])) / tenants_proj["ativos"] if tenants_proj["ativos"] else Decimal(1)
    limite = (dia + timedelta(days=HORIZONTES_DIAS[-1])).isoformat()
    esgotando = [{"fornecedor": linha["fornecedor"], "servico": linha["servico"], "data": linha["projecao"]["esgotamento_estimado"]}
                 for linha in linhas if linha["projecao"]["esgotamento_estimado"] and linha["projecao"]["esgotamento_estimado"] <= limite]
    return {
        "competencia": dados["competencia"], "componentes": linhas, "alertas_abertos": [alerta_dict(a) for a in alertas],
        "resumo": {
            "pool_provisionado_mensal": float(total_prov), "pool_real_mensal": infraestrutura._f(dados["real"]),
            "por_pool": dados["por_pool"], "alocado_tenants_mensal": float(dados["alocado_tenants"]),
            # capacidade contratada ainda não absorvida pela base (custo de capacidade ociosa da plataforma)
            "capacidade_nao_alocada_mensal": float(dados["capacidade_nao_alocada"]), "faltantes": dados["faltantes"],
            "reserva_mensal": float(total_prov - dados["real"]) if dados["real"] is not None else None,
            "unidades_ponderadas": float(dados["unidades"]), "tenants_alocados": tenants, "planos_sem_peso": dados["planos_sem_peso"],
            "receita_recorrente_mensal": float(mrr), "custo_sobre_receita": round(float(total_prov / mrr), 4) if mrr else None,
            "concentracao_por_fornecedor": {f: round(v, 4) for f, v in sorted(por_fornecedor.items())},
            "dependencia_maior_fornecedor": {"fornecedor": maior[0], "participacao": round(maior[1], 4)} if maior else None,
            "tenants": tenants_proj,
        },
        # Plano máximo: o custo provisionado não cai com uso baixo e só muda com decisão humana; ao esgotar a capacidade, o
        # custo seguinte é desconhecido até a CyberFort decidir (upgrade, contrato Enterprise, desconto, parceria).
        "projecao": {
            "horizonte_dias": tenants_proj["horizonte_dias"], "custo_infra_projetado_mensal": float(total_prov),
            "receita_recorrente_projetada_mensal": float(mrr * fator),
            "custo_sobre_receita_projetado": round(float(total_prov / (mrr * fator)), 4) if mrr else None,
            "esgotamentos_ate_180_dias": esgotando,
        },
    }
