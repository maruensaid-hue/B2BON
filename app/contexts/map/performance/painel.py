"""Painel de performance comercial do MAP (D-080): QUOTA → PIPELINE → ACTIVITY → CONVERSION → MRR → COMMISSION → LEARNING.

`calcular` monta o painel de um conjunto de representantes (um só, ou a equipe inteira) com um número FIXO de consultas
agrupadas — o custo não cresce com o número de representantes nem de negócios. Nenhum número é inventado: sem quota,
sem vínculo com o CRM ou sem dado, o campo fica vazio e o motivo aparece em `pendencias`.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.contexts.crm import contract as crm
from app.contexts.governo import contract as governo
from app.contexts.map.performance import campanha, configuracao, inteligencia, receita
from app.contexts.map.performance.tipos import Familia, SituacaoCarteira, Velocidade
from app.models.contrato_governo import ContratoGoverno, OportunidadeGoverno
from app.models.representante import Representante
from app.models.usuario import Usuario

ETAPAS = (("contato_efetivo", "contas_trabalhadas", "contatos_efetivos"), ("reuniao", "contatos_efetivos", "reunioes"),
          ("oportunidade_qualificada", "reunioes", "oportunidades_qualificadas"), ("proposta", "oportunidades_qualificadas", "propostas"),
          ("fechamento", "propostas", "fechamentos"))


def periodo_mes(competencia: str) -> tuple[datetime, datetime]:
    ano, mes = (int(p) for p in competencia.split("-"))
    inicio = datetime(ano, mes, 1)
    return inicio, inicio + timedelta(days=monthrange(ano, mes)[1])


def _pct(parte: float, todo: float) -> float | None:
    return round(parte / todo, 4) if todo else None


def _datetime(dia: date) -> datetime:
    return datetime.combine(dia, datetime.min.time())


def _usuarios(db: Session, representantes: list[Representante]) -> dict[int, Usuario]:
    ids = [r.usuario_id for r in representantes if r.usuario_id]
    return {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()} if ids else {}


def _atividade_por_rep(db: Session, representantes, usuarios, inicio: datetime, fim: datetime, definicoes: dict) -> dict[int, dict]:
    """Funil de atividade do CRM por representante (uma rodada de consultas por tenant operador — normalmente um)."""
    por_tenant = defaultdict(list)
    for rep in representantes:
        usuario = usuarios.get(rep.usuario_id)
        if usuario is not None:
            por_tenant[usuario.tenant_id].append(usuario.id)
    por_usuario = {}
    for tenant_id, ids in por_tenant.items():
        por_usuario.update(crm.atividade_comercial(db, tenant_id, ids, inicio, fim, definicoes))
    return {rep.id: por_usuario[rep.usuario_id] for rep in representantes if rep.usuario_id in por_usuario}


def _pipeline_por_rep(db: Session, representantes, usuarios, politica: dict, fim: datetime, hoje: date) -> dict[int, list[dict]]:
    por_tenant = defaultdict(list)
    for rep in representantes:
        usuario = usuarios.get(rep.usuario_id)
        if usuario is not None:
            por_tenant[usuario.tenant_id].append(usuario.id)
    rep_por_usuario = {rep.usuario_id: rep.id for rep in representantes if rep.usuario_id}
    definicoes, velocidade = politica["definicoes"], politica["velocidade"]
    agora = _datetime(hoje)
    resultado = defaultdict(list)
    for tenant_id, ids in por_tenant.items():
        for negocio in crm.pipeline_aberto_por_vendedor(db, tenant_id, ids):
            familia = politica["familia_por_oferta"].get(str(negocio["oferta_id"]), Familia.NAO_CLASSIFICADA.value)
            classe = velocidade["por_familia"].get(familia, Velocidade.CORE.value)
            fechamento_previsto = negocio["criado_em"] + timedelta(days=velocidade["dias"][classe])
            ultimo_toque = max(d for d in (negocio["ultima_acao_em"], negocio["atualizado_em"], negocio["criado_em"]) if d is not None)
            dias_sem_acao = (agora - ultimo_toque).days
            resultado[rep_por_usuario[negocio["usuario_id"]]].append({
                **negocio, "familia": familia, "velocidade": classe, "fechamento_previsto": fechamento_previsto.date(),
                "fecha_no_periodo": fechamento_previsto < fim, "dias_sem_acao": dias_sem_acao,
                "atualizada": dias_sem_acao <= definicoes["dias_oportunidade_atualizada"],
                "proposta_sem_atividade": negocio["proposta_em"] is not None and dias_sem_acao > definicoes["dias_proposta_sem_atividade"],
                "estagnada": dias_sem_acao > definicoes["dias_oportunidade_estagnada"],
                "valor_ponderado": round(negocio["valor"] * negocio["probabilidade"] / 100, 2)})
    return resultado


def _taxas(contagens: dict) -> dict:
    return {etapa: _pct(contagens[atual], contagens[anterior]) for etapa, anterior, atual in ETAPAS}


def _aprendizado(janela: dict[int, dict], politica: dict) -> dict:
    """Taxas observadas na janela; viram a base recomendada só com amostra mínima (senão vale o baseline da política)."""
    minimo, baseline = politica["aprendizado"]["amostra_minima"], politica["funil_baseline"]
    total = defaultdict(int)
    for contagens in janela.values():
        for campo, valor in contagens.items():
            total[campo] += valor

    def recomendadas(contagens: dict) -> dict:
        saida = {}
        for etapa, anterior, atual in ETAPAS:
            observada = _pct(contagens.get(atual, 0), contagens.get(anterior, 0))
            amostra = contagens.get(anterior, 0)
            saida[etapa] = {"baseline": baseline[etapa], "observada": observada, "amostra": amostra,
                            "recomendada": observada if observada is not None and amostra >= minimo else baseline[etapa],
                            "fonte": "OBSERVED" if observada is not None and amostra >= minimo else "BASELINE"}
        return saida

    return {"janela_dias": politica["aprendizado"]["janela_dias"], "amostra_minima": minimo,
            "equipe": recomendadas(total), "por_representante": {r: recomendadas(c) for r, c in janela.items()}}


def _governo(db: Session, representante_ids: list[int], inicio: datetime, fim: datetime, semana: tuple[datetime, datetime],
             politica: dict) -> dict[int, dict]:
    """Pipeline governamental por representante — separado do New MRR privado (2 consultas)."""
    fechados = governo.tipos.ESTAGIOS_FECHADOS
    nao_qualificado = politica["governo"]["estagio_nao_qualificado"]
    resultado = {r: {"qualificadas": 0, "pipeline_qualificado": 0.0, "pipeline_licenca": 0.0, "pipeline_assinatura_anual": 0.0,
                     "novas_qualificadas_semana": 0, "meta_semana": politica["governo"]["oportunidades_qualificadas_semana"],
                     "proximos_fechamentos": [], "bookings_mes": 0.0} for r in representante_ids}
    for op in (db.query(OportunidadeGoverno).filter(OportunidadeGoverno.representante_id.in_(representante_ids),
                                                    OportunidadeGoverno.estagio.notin_(list(fechados))).all()):
        linha = resultado[op.representante_id]
        if op.estagio == nao_qualificado:
            continue
        licenca, assinatura = float(op.valor_estimado_licenca or 0), float(op.valor_estimado_assinatura or 0)
        linha["qualificadas"] += 1
        linha["pipeline_licenca"] += licenca
        linha["pipeline_assinatura_anual"] += assinatura
        linha["pipeline_qualificado"] += licenca + assinatura + float(op.valor_estimado_servicos or 0)
        if semana[0] <= op.criado_em < semana[1]:
            linha["novas_qualificadas_semana"] += 1
        if op.data_prevista_fechamento:
            linha["proximos_fechamentos"].append({"id": op.id, "titulo": op.titulo, "entidade": op.entidade_governamental,
                                                  "estagio": op.estagio, "fechamento_previsto": op.data_prevista_fechamento})
    for contrato in (db.query(ContratoGoverno).filter(ContratoGoverno.representante_id.in_(representante_ids),
                                                     ContratoGoverno.assinado_em >= inicio.date(), ContratoGoverno.assinado_em < fim.date()).all()):
        resultado[contrato.representante_id]["bookings_mes"] += float(contrato.valor_licenca or 0) + float(contrato.valor_assinatura_anual or 0)
    for linha in resultado.values():
        linha["proximos_fechamentos"] = sorted(linha["proximos_fechamentos"], key=lambda o: o["fechamento_previsto"])[:3]
        for campo in ("pipeline_qualificado", "pipeline_licenca", "pipeline_assinatura_anual", "bookings_mes"):
            linha[campo] = round(linha[campo], 2)
    return resultado


def _mix(clientes: list[dict], politica: dict) -> dict:
    total = sum(c["valor"] for c in clientes)
    por_familia = defaultdict(float)
    for cliente in clientes:
        por_familia[cliente["familia"]] += cliente["valor"]
    alto_valor = sum(v for f, v in por_familia.items() if f in politica["mix"]["familias_alto_valor"])
    participacao = _pct(alto_valor, total)
    return {"por_familia": {f: {"valor": round(v, 2), "participacao": _pct(v, total), "alvo": politica["mix"]["alvo"].get(f)}
                            for f, v in sorted(por_familia.items())},
            "alto_valor_participacao": participacao, "alto_valor_minimo": politica["mix"]["alto_valor_minimo"],
            # Indicador, nunca bloqueio: vender o produto adequado ao cliente continua permitido.
            "mix_quality": None if participacao is None else ("OK" if participacao >= politica["mix"]["alto_valor_minimo"] else "LOW_TICKET_MIX")}


def _velocidade(pipeline: list[dict], ganhos: list[dict], politica: dict, governo_rep: dict) -> dict:
    classes = {v.value: {"negocios": 0, "pipeline_mrr": 0.0, "dias_padrao": politica["velocidade"]["dias"][v.value], "ciclo_medio_observado": None}
               for v in Velocidade}
    for negocio in pipeline:
        classes[negocio["velocidade"]]["negocios"] += 1
        classes[negocio["velocidade"]]["pipeline_mrr"] += negocio["valor"]
    ciclos = defaultdict(list)
    for ganho in ganhos:
        familia = politica["familia_por_oferta"].get(str(ganho["oferta_id"]), Familia.NAO_CLASSIFICADA.value)
        ciclos[politica["velocidade"]["por_familia"].get(familia, Velocidade.CORE.value)].append(ganho["dias_ciclo"])
    for classe, dias in ciclos.items():
        classes[classe]["ciclo_medio_observado"] = round(sum(dias) / len(dias), 1)
    # STRATEGIC (Government) mostra o pipeline governamental em TCV, nunca somado ao MRR privado.
    classes[Velocidade.STRATEGIC.value]["pipeline_governo_tcv"] = governo_rep["pipeline_qualificado"]
    for dados in classes.values():
        dados["pipeline_mrr"] = round(dados["pipeline_mrr"], 2)
    return classes


def _alvos_atividade(contagens: dict | None, alvos: dict) -> dict | None:
    if contagens is None:
        return None
    return {campo: {"realizado": contagens.get(campo, 0), "alvo": alvo, "pct": _pct(contagens.get(campo, 0), alvo)}
            for campo, alvo in alvos.items() if campo in contagens}


def _semana(hoje: date) -> tuple[datetime, datetime]:
    inicio = _datetime(hoje - timedelta(days=hoje.weekday()))
    return inicio, inicio + timedelta(days=7)


def calcular(db: Session, representantes: list[Representante], competencia: str, hoje: date) -> dict:
    """Painel de cada representante + agregado da equipe, numa rodada fixa de consultas."""
    politica, politica_comissao = configuracao.performance(db), configuracao.comissao_privada(db)
    inicio, fim = periodo_mes(competencia)
    semana, dia = _semana(hoje), (_datetime(hoje), _datetime(hoje) + timedelta(days=1))
    ids = [r.id for r in representantes]
    usuarios = _usuarios(db, representantes)
    quotas = configuracao.quotas(db, [competencia], ids)
    novos = receita.novos_clientes(db, ids, inicio, fim, politica)
    situacoes = receita.carteira(db, ids, hoje, politica_comissao)
    comissoes = receita.comissoes(db, ids)
    pipeline = _pipeline_por_rep(db, representantes, usuarios, politica, fim, hoje)
    definicoes = politica["definicoes"]
    funil_mes = _atividade_por_rep(db, representantes, usuarios, inicio, fim, definicoes)
    funil_semana = _atividade_por_rep(db, representantes, usuarios, *semana, definicoes)
    funil_dia = _atividade_por_rep(db, representantes, usuarios, *dia, definicoes)
    janela_inicio = _datetime(hoje - timedelta(days=politica["aprendizado"]["janela_dias"]))
    janela = _atividade_por_rep(db, representantes, usuarios, janela_inicio, dia[1], definicoes)
    ganhos_por_tenant = defaultdict(list)
    for rep in representantes:
        if rep.usuario_id in usuarios:
            ganhos_por_tenant[usuarios[rep.usuario_id].tenant_id].append(rep.usuario_id)
    ganhos = [g for t, u in ganhos_por_tenant.items() for g in crm.ganhos_por_vendedor(db, t, u, janela_inicio)]
    gov = _governo(db, ids, inicio, fim, semana, politica)
    campanhas = campanha.avaliar_todas(db, representantes, hoje, situacoes, pipeline, comissoes, politica)

    paineis = []
    for rep in representantes:
        quota = quotas.get((rep.id, competencia))
        clientes = [c for c in novos if c["representante_id"] == rep.id]
        realizado = round(sum(c["valor"] for c in clientes), 2)
        abertos = pipeline.get(rep.id, [])
        pipeline_mrr = round(sum(n["valor"] for n in abertos), 2)
        quota_valor = quota.valor if quota else None
        multiplo = (quota.multiplo_cobertura if quota and quota.multiplo_cobertura else politica["cobertura"]["multiplo_padrao"])
        pipeline_alvo = (quota.pipeline_alvo or multiplo * quota_valor) if quota_valor else None
        forecast = round(realizado + sum(n["valor_ponderado"] for n in abertos if n["fecha_no_periodo"]), 2)
        carteira_rep = [s for s in situacoes if s["representante_id"] == rep.id]
        situacao_por_tenant = {s["tenant_id"]: s["situacao"] for s in carteira_rep}
        comissao = receita.resumo_comissao([c for c in comissoes if c["representante_id"] == rep.id], situacao_por_tenant, politica_comissao)
        mes = funil_mes.get(rep.id)
        painel = {
            "representante": {"id": rep.id, "nome": rep.nome, "usuario_id": rep.usuario_id, "vinculado_crm": rep.usuario_id in usuarios},
            "competencia": competencia,
            "quota": quota_valor, "quota_versao": quota.versao if quota else None, "realizado_new_mrr": realizado,
            "attainment": _pct(realizado, quota_valor) if quota_valor else None,
            "gap": round(max(quota_valor - realizado, 0), 2) if quota_valor else None,
            "pipeline": {"qualificado_mrr": pipeline_mrr, "ponderado_mrr": round(sum(n["valor_ponderado"] for n in abertos), 2),
                         "alvo": round(pipeline_alvo, 2) if pipeline_alvo else None, "multiplo_alvo": multiplo,
                         "cobertura": _pct(pipeline_mrr, quota_valor) if quota_valor else None,
                         "negocios": len(abertos), "atualizadas_pct": _pct(sum(1 for n in abertos if n["atualizada"]), len(abertos))},
            "forecast_new_mrr": forecast,
            "fechado_crm_mrr": mes["valor_fechado"] if mes else None,  # ganho no CRM, ainda sem 1ª mensalidade = não é New MRR
            "ticket_medio": round(realizado / len(clientes), 2) if clientes else None,
            "ticket_medio_baseline": politica["ticket_medio_baseline"],
            "novos_clientes": [{k: c[k] for k in ("cliente", "valor", "plano", "familia", "primeiro_pagamento_em")} for c in clientes],
            "mix": _mix(clientes, politica),
            "funil_mes": mes, "taxas_mes": _taxas(mes) if mes else None, "funil_baseline": politica["funil_baseline"],
            "atividade": {"dia": _alvos_atividade(funil_dia.get(rep.id), politica["atividade"]["diaria"]),
                          "semana": _alvos_atividade(funil_semana.get(rep.id), politica["atividade"]["semanal"])},
            "velocidade": _velocidade(abertos, [g for g in ganhos if g["usuario_id"] == rep.usuario_id], politica, gov[rep.id]),
            "comissao": comissao,
            "carteira": {s.value: sum(1 for c in carteira_rep if c["situacao"] == s.value) for s in SituacaoCarteira},
            "governo": gov[rep.id],
            "campanhas": [c["por_representante"][rep.id] | {"codigo": c["codigo"], "nome": c["nome"]} for c in campanhas],
            "pendencias": ([] if quota else ["Quota NEW_MRR da competência"]) + ([] if rep.usuario_id in usuarios else
                                                                                ["Vincular o representante a um usuário do CRM"]),
        }
        painel["alertas"] = inteligencia.alertas(painel, abertos, politica)
        painel["_pipeline"] = abertos
        paineis.append(painel)
    return {"competencia": competencia, "paineis": paineis, "aprendizado": _aprendizado(janela, politica), "campanhas": campanhas,
            "equipe": _equipe(paineis, campanhas)}


def _equipe(paineis: list[dict], campanhas: list[dict]) -> dict:
    quota = sum(p["quota"] or 0 for p in paineis)
    realizado = round(sum(p["realizado_new_mrr"] for p in paineis), 2)
    pipeline = round(sum(p["pipeline"]["qualificado_mrr"] for p in paineis), 2)
    return {"representantes": len(paineis), "quota": quota, "realizado_new_mrr": realizado, "attainment": _pct(realizado, quota),
            "gap": round(max(quota - realizado, 0), 2), "pipeline_mrr": pipeline, "cobertura": _pct(pipeline, quota),
            "forecast_new_mrr": round(sum(p["forecast_new_mrr"] for p in paineis), 2),
            "governo_pipeline_qualificado": round(sum(p["governo"]["pipeline_qualificado"] for p in paineis), 2),
            "campanhas": [{"codigo": c["codigo"], **c["equipe"]} for c in campanhas]}
