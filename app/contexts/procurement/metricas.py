"""Indicadores do lado comprador (Fase 16): ciclo de contratação, execução
do PCA, desempenho de fornecedores e risco de renovação de contratos.

Ficam dentro do contexto `procurement` (barreira Buy/Sell): nenhum dado
daqui chega às métricas de receita do lado vendedor. Mesmo contrato de
métrica: valor, unidade, metodologia e amostra; sem dado, `None`.
"""

from datetime import date
from statistics import median

from sqlalchemy.orm import Session

from app.contexts.procurement import planejamento
from app.contexts.procurement.tipos import STATUS_PROCESSO_FINAIS
from app.models.contrato_compra import ContratoCompra
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.fornecedor_compras import FornecedorCompras
from app.models.item_pca import ItemPca
from app.models.plano_contratacao import PlanoContratacao
from app.models.processo_contratacao import ProcessoContratacao

DIAS_RENOVACAO = 120


def _metrica(valor, unidade: str, metodologia: str, amostra: int, **detalhe) -> dict:
    return {"valor": valor, "unidade": unidade, "metodologia": metodologia, "amostra": amostra, **detalhe}


def _taxa(parte: float, total: float) -> float | None:
    return round(parte / total, 4) if total else None


def ciclo_contratacao(db: Session, tenant_id: str, hoje: date) -> dict:
    processos = db.query(ProcessoContratacao).filter_by(tenant_id=tenant_id).all()
    primeiro_contrato: dict[int, date] = {}
    for c in db.query(ContratoCompra).filter(ContratoCompra.tenant_id == tenant_id, ContratoCompra.processo_id.isnot(None)).all():
        assinado = (c.criado_em.date() if c.criado_em else None) or c.vigencia_inicio
        if assinado and (c.processo_id not in primeiro_contrato or assinado < primeiro_contrato[c.processo_id]):
            primeiro_contrato[c.processo_id] = assinado
    ciclos = [(primeiro_contrato[p.id] - p.criado_em.date()).days for p in processos if p.id in primeiro_contrato and p.criado_em]
    em_andamento = [(hoje - p.criado_em.date()).days for p in processos
                    if p.id not in primeiro_contrato and p.status not in STATUS_PROCESSO_FINAIS and p.criado_em]
    return _metrica(
        median(ciclos) if ciclos else None, "dias",
        "Mediana de dias entre a abertura do processo e o registro do primeiro contrato dele. Processos em andamento "
        "entram só na idade (não têm fim ainda).",
        len(ciclos), concluidos=len(ciclos), minimo=min(ciclos) if ciclos else None, maximo=max(ciclos) if ciclos else None,
        em_andamento=len(em_andamento), idade_mediana_em_andamento=median(em_andamento) if em_andamento else None,
    )


def execucao_pca(db: Session, tenant_id: str, hoje: date) -> dict:
    planos = db.query(PlanoContratacao).filter_by(tenant_id=tenant_id).order_by(PlanoContratacao.ano.desc()).all()
    por_plano = []
    for plano in planos:
        painel = planejamento.painel(db, tenant_id, plano, hoje)
        itens = db.query(ItemPca).filter(ItemPca.tenant_id == tenant_id, ItemPca.plano_id == plano.id, ItemPca.status != "CANCELADO").all()
        contratados = sum(1 for i in itens if i.status == "CONTRATADO")
        por_plano.append({
            "plano_id": plano.id, "ano": plano.ano, "nome": plano.nome,
            "itens": len(itens), "itens_contratados": contratados, "execucao_itens": _taxa(contratados, len(itens)),
            "valor_planejado": painel["valor_planejado"], "valor_contratado": painel["contratado"],
            "execucao_valor": _taxa(painel["contratado"], painel["valor_planejado"]),
            "pago_sobre_contratado": painel["percentual_execucao"], "processos_atrasados": len(painel["processos_atrasados"]),
        })
    atual = next((p for p in por_plano if p["ano"] == hoje.year), por_plano[0] if por_plano else None)
    return _metrica(
        atual["execucao_valor"] if atual else None, "taxa",
        "Valor contratado / valor planejado do PCA (itens não cancelados), no plano do ano corrente. Também por itens "
        "e pago sobre contratado.",
        atual["itens"] if atual else 0, plano_referencia=atual["plano_id"] if atual else None, por_plano=por_plano,
    )


def desempenho_fornecedores(db: Session, tenant_id: str) -> dict:
    fornecedores = {f.id: f for f in db.query(FornecedorCompras).filter_by(tenant_id=tenant_id).all()}
    contratos = db.query(ContratoCompra).filter_by(tenant_id=tenant_id).all()
    eventos = db.query(EventoContratoCompra).filter_by(tenant_id=tenant_id).all()
    por_fornecedor: dict[int, dict] = {}
    for c in contratos:
        item = por_fornecedor.setdefault(c.fornecedor_id, {"contratos": 0, "valor": 0.0, "acrescimos": []})
        item["contratos"] += 1
        item["valor"] += c.valor_atual or 0
        if c.valor_inicial and c.valor_atual is not None:
            item["acrescimos"].append(c.valor_atual / c.valor_inicial - 1)
    notas: dict[int, list[float]] = {}
    ocorrencias: dict[int, int] = {}
    entregas: dict[int, int] = {}
    for e in eventos:
        if e.tipo == "FISCALIZACAO" and e.nota is not None:
            notas.setdefault(e.fornecedor_id, []).append(e.nota)
        elif e.tipo == "OCORRENCIA":
            ocorrencias[e.fornecedor_id] = ocorrencias.get(e.fornecedor_id, 0) + 1
        elif e.tipo == "ENTREGA":
            entregas[e.fornecedor_id] = entregas.get(e.fornecedor_id, 0) + 1
    itens = []
    for fid in set(por_fornecedor) | set(notas) | set(ocorrencias):
        base = por_fornecedor.get(fid, {"contratos": 0, "valor": 0.0, "acrescimos": []})
        lista = notas.get(fid, [])
        itens.append({
            "fornecedor_id": fid, "razao_social": fornecedores[fid].razao_social if fid in fornecedores else None,
            "contratos": base["contratos"], "valor_contratado": round(base["valor"], 2),
            "nota_media_fiscalizacao": round(sum(lista) / len(lista), 2) if lista else None, "fiscalizacoes": len(lista),
            "ocorrencias": ocorrencias.get(fid, 0), "entregas": entregas.get(fid, 0),
            "acrescimo_medio": round(sum(base["acrescimos"]) / len(base["acrescimos"]), 4) if base["acrescimos"] else None,
        })
    itens.sort(key=lambda x: (x["nota_media_fiscalizacao"] is None, -(x["nota_media_fiscalizacao"] or 0), x["ocorrencias"]))
    todas = [n for lista in notas.values() for n in lista]
    return _metrica(
        round(sum(todas) / len(todas), 2) if todas else None, "nota",
        "Nota média das fiscalizações registradas; por fornecedor também ocorrências, entregas e acréscimo médio por "
        "aditivo. Sem fiscalização registrada, a nota fica vazia (não é zero).",
        len(todas), por_fornecedor=itens,
    )


def risco_renovacao(db: Session, tenant_id: str, hoje: date) -> dict:
    vigentes = db.query(ContratoCompra).filter_by(tenant_id=tenant_id, status="VIGENTE").all()
    processos_abertos = db.query(ProcessoContratacao).filter(
        ProcessoContratacao.tenant_id == tenant_id, ProcessoContratacao.status.notin_(STATUS_PROCESSO_FINAIS)).all()
    categorias_em_processo = {p.categoria for p in processos_abertos if p.categoria}
    itens = []
    for c in vigentes:
        if c.vigencia_fim is None or (c.vigencia_fim - hoje).days > DIAS_RENOVACAO:
            continue
        dias = (c.vigencia_fim - hoje).days
        sucessor = bool(c.categoria and c.categoria in categorias_em_processo)
        nivel = "ALTO" if c.necessidade_continuada and not sucessor and dias <= 60 else "MEDIO" if c.necessidade_continuada and not sucessor else "BAIXO"
        itens.append({"contrato_id": c.id, "objeto": c.objeto, "dias_para_fim": dias, "valor_atual": c.valor_atual,
                      "necessidade_continuada": c.necessidade_continuada, "processo_sucessor_em_andamento": sucessor, "risco": nivel})
    itens.sort(key=lambda x: x["dias_para_fim"])
    em_risco = [i for i in itens if i["risco"] != "BAIXO"]
    return _metrica(
        len(em_risco), "contratos",
        f"Contratos vigentes que vencem em até {DIAS_RENOVACAO} dias, com necessidade continuada e sem processo da "
        "mesma categoria em andamento. ALTO quando faltam 60 dias ou menos. Sinal para revisão, não conclusão.",
        len(vigentes), vencendo=len(itens), sem_data_de_fim=sum(1 for c in vigentes if c.vigencia_fim is None), contratos=itens,
    )


def metricas(db: Session, tenant_id: str, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    return {
        "procurement_cycle_time": ciclo_contratacao(db, tenant_id, hoje),
        "pca_execution": execucao_pca(db, tenant_id, hoje),
        "supplier_performance": desempenho_fornecedores(db, tenant_id),
        "contract_renewal_risk": risco_renovacao(db, tenant_id, hoje),
    }
