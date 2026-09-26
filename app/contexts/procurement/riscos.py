"""Procurement Risk Engine (§46).

Sinal de risco NÃO é irregularidade: é um sinal analítico que requer
revisão humana. As mensagens usam "requer revisão", "sinal analítico" e
"possível inconsistência"; nunca conclusão jurídica. Limites que dependem
de regime jurídico (ex.: fragmentação) só são avaliados se o órgão os
configurou; senão, aparecem em `nao_avaliados`.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.contexts.procurement import contratos as contratos_intel
from app.contexts.procurement import precos, repositorio
from app.contexts.procurement.fluxo import LEI_14133
from app.contexts.procurement.tipos import STATUS_PROCESSO_FINAIS
from app.contexts.shared.texto import termos_em_comum
from app.models.contrato_compra import ContratoCompra
from app.models.evento_contrato_compra import EventoContratoCompra
from app.models.item_pca import ItemPca
from app.models.orgao_publico import OrgaoPublico
from app.models.processo_contratacao import ProcessoContratacao

AVISO = "Sinais analíticos para revisão humana. Não indicam irregularidade."
DIAS_CONTRATO = LEI_14133.parametro("dias_alerta_contrato")  # padrão; o órgão pode configurar
DIAS_PLANEJAMENTO = 60
ACRESCIMO_ALERTA = 0.25
ADITIVOS_ALERTA = 3
CONCENTRACAO_ALERTA = 0.5
DESVIO_ORCAMENTO = LEI_14133.parametro("desvio_orcamento")


def _sinal(tipo: str, severidade: str, mensagem: str, entidade: str, entidade_id: int, evidencia: dict) -> dict:
    return {"tipo": tipo, "severidade": severidade, "mensagem": mensagem, "entidade_tipo": entidade,
            "entidade_id": entidade_id, "evidencia": evidencia, "natureza": "sinal_analitico_requer_revisao"}


def sinais(db: Session, tenant_id: str, hoje: date | None = None, processo_id: int | None = None) -> dict:
    hoje = hoje or date.today()
    resultado: list[dict] = []
    nao_avaliados: list[str] = []
    processos = db.query(ProcessoContratacao).filter_by(tenant_id=tenant_id).all()
    abertos = [p for p in processos if p.status not in STATUS_PROCESSO_FINAIS]
    contratos = db.query(ContratoCompra).filter_by(tenant_id=tenant_id).all()
    orgaos = {o.id: o for o in db.query(OrgaoPublico).filter_by(tenant_id=tenant_id).all()}
    tipos_por_processo = repositorio.COMPRA.tipos_de_documento(db, tenant_id)  # uma consulta, sem arquivo (S0/S2)
    # Phase D (TD-090): itens do PCA, pesquisas de preço e eventos de contrato em uma consulta cada
    ids_item = {p.item_pca_id for p in abertos if p.item_pca_id}
    itens_pca = {i.id: i for i in db.query(ItemPca).filter(ItemPca.tenant_id == tenant_id, ItemPca.id.in_(ids_item))} if ids_item else {}
    precos_por_processo = precos.resumo_por_processo(
        db, tenant_id, [p.id for p in abertos if p.status in ("PESQUISA_PRECOS", "APROVACAO", "PUBLICADO")])
    intel_contratos = contratos_intel.inteligencia_em_lote(db, tenant_id, contratos, hoje)

    for i, a in enumerate(abertos):
        for b in abertos[i + 1:]:
            if (a.categoria == b.categoria or not a.categoria or not b.categoria) and termos_em_comum(a.objeto, b.objeto):
                resultado.append(_sinal("DUPLICATE_PROCUREMENT", "ATENCAO",
                                        f"Possível inconsistência: os processos {a.id} e {b.id} têm objetos semelhantes. Requer revisão.",
                                        "processo_contratacao", a.id, {"processos": [a.id, b.id]}))

    for p in abertos:
        if p.prazo_previsto and p.prazo_previsto < hoje:
            resultado.append(_sinal("PROCESS_DELAY", "ATENCAO",
                                    f"Processo {p.numero or p.id} além do prazo previsto ({p.prazo_previsto:%d/%m/%Y}). Requer revisão.",
                                    "processo_contratacao", p.id, {"prazo_previsto": p.prazo_previsto, "status": p.status}))
        item = itens_pca.get(p.item_pca_id) if p.item_pca_id else None
        if item is None and p.valor_estimado:
            resultado.append(_sinal("BUDGET_MISMATCH", "INFO", "Sinal analítico: processo sem vínculo com item do PCA. Requer revisão.",
                                    "processo_contratacao", p.id, {"valor_estimado": p.valor_estimado}))
        elif item is not None and p.valor_estimado and item.valor_estimado and p.valor_estimado > item.valor_estimado * (1 + DESVIO_ORCAMENTO):
            resultado.append(_sinal("BUDGET_MISMATCH", "ATENCAO",
                                    f"Possível inconsistência: valor do processo {p.valor_estimado:,.2f} acima do planejado no PCA "
                                    f"({item.valor_estimado:,.2f}). Requer revisão.", "processo_contratacao", p.id,
                                    {"valor_processo": p.valor_estimado, "valor_pca": item.valor_estimado, "item_pca_id": item.id}))
        esperados = LEI_14133.documentos(p.status)
        if esperados:
            presentes = tipos_por_processo.get(p.id, set())
            faltam = [t for t in esperados if t not in presentes]
            if faltam:
                resultado.append(_sinal("MISSING_DOCUMENTATION", "ATENCAO",
                                        f"Documentação possivelmente incompleta para a etapa {p.status}: {', '.join(faltam)}. Requer revisão.",
                                        "processo_contratacao", p.id, {"faltam": faltam, "etapa": p.status}))
        if p.status in ("PESQUISA_PRECOS", "APROVACAO", "PUBLICADO"):
            for item_preco in precos_por_processo.get(p.id, []):
                if not item_preco["suficiente"] or item_preco["fora_da_faixa"]:
                    resultado.append(_sinal("PRICE_DEVIATION", "ATENCAO",
                                            f"Sinal analítico na pesquisa de preços de \"{item_preco['item']}\": "
                                            + ("poucas amostras" if not item_preco["suficiente"] else "cotações fora da faixa da mediana")
                                            + ". Requer revisão.", "processo_contratacao", p.id, item_preco))

    for c in contratos:
        intel = intel_contratos[c.id]
        dias_param = LEI_14133.parametro("dias_alerta_contrato", orgaos[c.orgao_id].parametros if orgaos.get(c.orgao_id) else None)
        if c.status == "VIGENTE" and intel["dias_para_fim"] is not None and 0 <= intel["dias_para_fim"] <= dias_param and c.necessidade_continuada:
            sucessor = next((p for p in abertos if termos_em_comum(c.objeto, p.objeto)), None)
            if sucessor is None:
                resultado.append(_sinal("CONTRACT_EXPIRING", "ALTA",
                                        f"Contrato vence em {intel['dias_para_fim']} dias e existe necessidade continuada, mas não foi "
                                        "localizado processo sucessor. Requer revisão.", "contrato_compra", c.id,
                                        {"vigencia_fim": c.vigencia_fim, "dias_para_fim": intel["dias_para_fim"]}))
        if intel["aditivos"] >= ADITIVOS_ALERTA or (intel["acrescimo_percentual"] or 0) > ACRESCIMO_ALERTA:
            resultado.append(_sinal("REPEATED_AMENDMENTS", "ATENCAO",
                                    f"Sinal analítico: {intel['aditivos']} aditivo(s), acréscimo de "
                                    f"{(intel['acrescimo_percentual'] or 0) * 100:.0f}% sobre o valor inicial. Requer revisão.",
                                    "contrato_compra", c.id, {"aditivos": intel["aditivos"], "acrescimo": intel["acrescimo_percentual"]}))
        notas = [e["nota"] for e in intel["eventos"] if e["tipo"] == "FISCALIZACAO" and e["nota"] is not None]
        recentes = [e for e in intel["eventos"] if e["tipo"] == "OCORRENCIA" and e["data"] and e["data"] >= hoje - timedelta(days=90)]
        if (len(notas) >= 3 and notas[-3] > notas[-2] > notas[-1]) or len(recentes) >= 3:
            resultado.append(_sinal("SLA_DETERIORATION", "ATENCAO",
                                    "Sinal analítico: desempenho do fornecedor em queda nas últimas fiscalizações ou ocorrências "
                                    "recorrentes. Requer revisão.", "contrato_compra", c.id,
                                    {"ultimas_notas": notas[-3:], "ocorrencias_90d": len(recentes)}))

    por_categoria: dict[str, list[ContratoCompra]] = {}
    for c in contratos:
        if c.categoria:
            por_categoria.setdefault(c.categoria, []).append(c)
    for categoria, lista in por_categoria.items():
        total = sum(c.valor_atual or 0 for c in lista)
        if len(lista) >= 3 and total:
            por_fornecedor: dict[int, float] = {}
            for c in lista:
                por_fornecedor[c.fornecedor_id] = por_fornecedor.get(c.fornecedor_id, 0) + (c.valor_atual or 0)
            fornecedor_id, valor = max(por_fornecedor.items(), key=lambda kv: kv[1])
            if valor / total > CONCENTRACAO_ALERTA:
                resultado.append(_sinal("SUPPLIER_CONCENTRATION", "INFO",
                                        f"Sinal analítico: um fornecedor concentra {valor / total:.0%} do valor contratado em \"{categoria}\". "
                                        "Requer revisão.", "fornecedor_compras", fornecedor_id, {"categoria": categoria, "participacao": round(valor / total, 3)}))

    for orgao in orgaos.values():
        limite = LEI_14133.parametro("limite_fragmentacao", orgao.parametros)
        if limite is None:
            nao_avaliados.append(f"PROCUREMENT_FRAGMENTATION ({orgao.nome}): limite não configurado para o regime do órgão.")
            continue
        diretas: dict[tuple, list[ProcessoContratacao]] = {}
        for p in processos:
            if p.orgao_id == orgao.id and p.modalidade == "DIRECT_AWARD" and p.categoria and p.status != "CANCELADO":
                diretas.setdefault((p.categoria, p.criado_em.year), []).append(p)
        for (categoria, ano), lista in diretas.items():
            soma = sum(p.valor_estimado or 0 for p in lista)
            if len(lista) >= 2 and soma > limite:
                resultado.append(_sinal("PROCUREMENT_FRAGMENTATION", "ATENCAO",
                                        f"Possível inconsistência: {len(lista)} contratações diretas de \"{categoria}\" em {ano} somam "
                                        f"{soma:,.2f}, acima do limite configurado. Requer revisão.", "orgao_publico", orgao.id,
                                        {"processos": [p.id for p in lista], "limite": limite, "soma": soma}))

    for item in db.query(ItemPca).filter_by(tenant_id=tenant_id, status="PLANEJADO").all():
        tem_processo = any(p.item_pca_id == item.id for p in abertos)
        if item.data_prevista and item.data_prevista <= hoje + timedelta(days=DIAS_PLANEJAMENTO) and not tem_processo:
            resultado.append(_sinal("INCOMPLETE_PLANNING", "ALTA" if item.data_prevista < hoje else "ATENCAO",
                                    f"Item do PCA \"{item.descricao}\" previsto para {item.data_prevista:%d/%m/%Y} sem processo ativo. Requer revisão.",
                                    "item_pca", item.id, {"data_prevista": item.data_prevista}))

    if processo_id is not None:
        resultado = [s for s in resultado if (s["entidade_tipo"] == "processo_contratacao" and s["entidade_id"] == processo_id)
                     or processo_id in s["evidencia"].get("processos", [])]
    ordem = {"ALTA": 0, "ATENCAO": 1, "INFO": 2}
    resultado.sort(key=lambda s: ordem[s["severidade"]])
    return {"aviso": AVISO, "sinais": resultado, "nao_avaliados": nao_avaliados}
