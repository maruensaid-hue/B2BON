"""Indicadores administrativos do gerenciador de recursos: quanto do que foi entregue veio de fonte gratuita, quanto custo de provedor pago isso evitou e
como cada fonte se comporta. Só super_admin vê, e só valores medidos: nada é inventado.

Chaves internas genéricas (nunca o nome de um fornecedor): `FREE_RESOURCE_UTILIZATION_RATE` e `PAID_PROVIDER_COST_AVOIDED`.

O custo evitado é uma ESTIMATIVA e diz como foi feita: decisores que a fonte gratuita entregou × a média histórica de créditos do provedor pago por decisor
(medida nas pesquisas que só usaram o pago) × o custo unitário da política vigente na pesquisa. Sem histórico medido ou sem custo aprovado, o valor é
`None` com o motivo, nunca zero nem um número presumido."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import gerenciador, precos
from app.contexts.enriquecimento.config import agora_utc, obter_politica
from app.models.enriquecimento_creditos import PesquisaDecisores, PesquisaDecisoresEmpresa
from app.models.enriquecimento_fontes import EnriquecimentoConsulta, EnriquecimentoFonte


def _fontes(db: Session, agora: datetime) -> list[dict]:
    gerenciador.garantir_padrao(db)
    saida = []
    for f in db.query(EnriquecimentoFonte).order_by(EnriquecimentoFonte.prioridade, EnriquecimentoFonte.codigo).all():
        consumido = f.consumido_periodo if f.periodo == gerenciador.periodo_de(agora) else 0  # mês virou e ninguém consultou ainda: o consumo é zero
        saida.append({
            "codigo": f.codigo, "camada": f.camada, "ativo": f.ativo, "prioridade": f.prioridade, "limite_mensal": f.limite_mensal, "consumido_periodo": consumido,
            "restante_periodo": None if f.limite_mensal is None else max(f.limite_mensal - consumido, 0), "permite_uso_comercial": f.permite_uso_comercial,
            "suspensa_ate": f.suspensa_ate if f.suspensa_ate and f.suspensa_ate > agora else None, "falhas_seguidas": f.falhas_seguidas,
            "ultima_consulta_em": f.ultima_consulta_em,
        })
    return saida


def _por_fonte(db: Session, desde: datetime, ate: datetime) -> list[dict]:
    soma = func.coalesce
    linhas = db.query(
        EnriquecimentoConsulta.fonte, EnriquecimentoConsulta.estado, EnriquecimentoConsulta.motivo, func.count(EnriquecimentoConsulta.id),
        soma(func.sum(EnriquecimentoConsulta.encontrados), 0), soma(func.sum(EnriquecimentoConsulta.novos), 0),
        soma(func.sum(EnriquecimentoConsulta.creditos_fonte), 0), soma(func.avg(EnriquecimentoConsulta.duracao_ms), 0),
    ).filter(EnriquecimentoConsulta.criado_em >= desde, EnriquecimentoConsulta.criado_em < ate).group_by(
        EnriquecimentoConsulta.fonte, EnriquecimentoConsulta.estado, EnriquecimentoConsulta.motivo).all()
    fontes: dict[str, dict] = {}
    for fonte, estado, motivo, n, encontrados, novos, creditos, duracao in linhas:
        f = fontes.setdefault(fonte, {"fonte": fonte, "consultas": 0, "ok": 0, "sem_resultados": 0, "erro": 0, "ignoradas": 0, "cache": 0, "encontrados": 0,
                                      "novos": 0, "creditos_fonte": 0, "_ms": 0.0})
        if estado == "ignorada":
            f["ignoradas"] += n
            f["cache"] += n if motivo == "cache" else 0
            continue
        f["consultas"] += n
        f[estado] = f.get(estado, 0) + n
        f["encontrados"] += int(encontrados)
        f["novos"] += int(novos)
        f["creditos_fonte"] += int(creditos)
        f["_ms"] += float(duracao) * n
    for f in fontes.values():
        consultas, milissegundos = f["consultas"], f.pop("_ms")
        f["taxa_sucesso"] = None if not consultas else round((f["ok"] + f["sem_resultados"]) / consultas, 4)  # resposta válida, com ou sem contatos
        f["taxa_com_resultado"] = None if not consultas else round(f["ok"] / consultas, 4)
        f["latencia_media_ms"] = None if not consultas else round(milissegundos / consultas)
    return sorted(fontes.values(), key=lambda f: f["fonte"])


def _media_historica_creditos_por_decisor(db: Session) -> Decimal | None:
    """Créditos do provedor pago POR decisor, medidos nas empresas atendidas só por ele (sem nenhuma consulta gratuita com resultado)."""
    com_gratuito = db.query(EnriquecimentoConsulta.item_id).filter(
        EnriquecimentoConsulta.item_id.isnot(None), EnriquecimentoConsulta.estado == "ok", EnriquecimentoConsulta.encontrados > 0)
    medidos, retornados = db.query(
        func.coalesce(func.sum(PesquisaDecisoresEmpresa.provedor_medidos), 0), func.coalesce(func.sum(PesquisaDecisoresEmpresa.decisores_retornados), 0),
    ).filter(
        PesquisaDecisoresEmpresa.estado == "concluido", PesquisaDecisoresEmpresa.provedor_medidos > 0, PesquisaDecisoresEmpresa.decisores_retornados > 0,
        PesquisaDecisoresEmpresa.id.notin_(com_gratuito),
    ).one()
    return Decimal(int(medidos)) / Decimal(int(retornados)) if int(retornados) else None


def visao(db: Session, dias: int = 30, agora: datetime | None = None) -> dict:
    agora = agora or agora_utc()
    desde = agora - timedelta(days=max(1, dias))
    ate = agora + timedelta(seconds=1)

    gratis_por_item: dict[int, int] = {
        item_id: int(total) for item_id, total in db.query(EnriquecimentoConsulta.item_id, func.sum(EnriquecimentoConsulta.encontrados)).filter(
            EnriquecimentoConsulta.item_id.isnot(None), EnriquecimentoConsulta.estado == "ok", EnriquecimentoConsulta.criado_em >= desde,
            EnriquecimentoConsulta.criado_em < ate).group_by(EnriquecimentoConsulta.item_id).all()}
    itens = db.query(PesquisaDecisoresEmpresa).filter(
        PesquisaDecisoresEmpresa.estado == "concluido", PesquisaDecisoresEmpresa.atualizado_em >= desde, PesquisaDecisoresEmpresa.atualizado_em < ate).all()
    gratuitos = pagos = 0
    evitados_por_politica: dict[int | None, int] = {}
    for item in itens:
        gratis = min(gratis_por_item.get(item.id, 0), item.decisores_retornados)
        gratuitos += gratis
        pagos += item.decisores_retornados - gratis
        if gratis:
            politica_id = db.query(PesquisaDecisores.politica_id).filter(PesquisaDecisores.id == item.pesquisa_id).scalar()
            evitados_por_politica[politica_id] = evitados_por_politica.get(politica_id, 0) + gratis
    entregues = gratuitos + pagos

    media = _media_historica_creditos_por_decisor(db)
    evitados = sum(evitados_por_politica.values())
    custo_evitado: Decimal | None = None
    motivo_sem_valor, creditos_evitados = None, None
    if evitados == 0:
        motivo_sem_valor = "nenhum_decisor_atendido_por_fonte_gratuita_no_periodo"
    elif media is None:
        motivo_sem_valor = "sem_historico_medido_do_provedor_pago"
    else:
        creditos_evitados = (media * evitados).quantize(Decimal("0.01"))
        total = Decimal(0)
        for politica_id, quantidade in evitados_por_politica.items():
            unitario = obter_politica(db, politica_id).custo_unitario_brl if politica_id else None
            if unitario is None:
                total, motivo_sem_valor = None, "politica_sem_custo_unitario_aprovado"
                break
            total += precos.valor(1, unitario) * media * quantidade
        custo_evitado = None if total is None else precos.exibir(total)

    return {
        "periodo": {"desde": desde, "ate": agora, "dias": dias},
        "decisores_entregues": {"total": entregues, "por_fonte_gratuita": gratuitos, "por_provedor_pago": pagos},
        "FREE_RESOURCE_UTILIZATION_RATE": None if not entregues else round(gratuitos / entregues, 4),
        "PAID_PROVIDER_COST_AVOIDED": {
            "estimativa": True,
            "valor_brl": None if custo_evitado is None else str(custo_evitado),
            "creditos_do_provedor_evitados": None if creditos_evitados is None else str(creditos_evitados),
            "media_historica_creditos_por_decisor": None if media is None else str(media.quantize(Decimal("0.0001"))),
            "motivo_sem_valor": motivo_sem_valor,
            "metodo": "decisores entregues por fonte gratuita × média histórica medida de créditos do provedor pago por decisor × custo unitário da política",
        },
        "fontes": _fontes(db, agora),
        "desempenho_por_fonte": _por_fonte(db, desde, ate),
    }
