"""AI FinOps Dashboard (Fase 5, §57).

Tudo calculado do ledger (`registro_uso_ia`). Métricas sem base honesta
voltam `None` com o motivo em `indisponivel` — nunca um número inventado:
- AI Revenue / Gross Profit / Gross Margin: dependem do preço do crédito
  ao cliente (política pendente e preços da Fase 14/15);
- AI Cost / Bid e / Procurement Process: módulos das Fases 9–10;
- AI Cost / Revenue Generated: custo em USD × receita em BRL exige
  câmbio configurado (`FINOPS_CAMBIO_USD_BRL`).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.finops import creditos
from app.core.config import settings
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.reuniao import Reuniao


def _d(valor) -> float:
    return float(Decimal(str(valor or 0)))


def _agrupar(db: Session, coluna, filtros) -> list[dict]:
    linhas = (
        db.query(coluna, func.count(RegistroUsoIa.id), func.sum(RegistroUsoIa.custo_usd),
                 func.sum(RegistroUsoIa.tokens_entrada), func.sum(RegistroUsoIa.tokens_saida),
                 func.sum(RegistroUsoIa.tokens_cache_leitura), func.sum(RegistroUsoIa.creditos_consumidos))
        .filter(*filtros)
        .group_by(coluna)
        .all()
    )
    return sorted(
        (
            {"chave": chave, "chamadas": n, "custo_usd": _d(c), "tokens_entrada": int(te or 0), "tokens_saida": int(ts or 0),
             "tokens_cache_leitura": int(tc or 0), "creditos": _d(cr)}
            for chave, n, c, te, ts, tc, cr in linhas
        ),
        key=lambda item: -item["custo_usd"],
    )


def resumo(db: Session, inicio: datetime, fim: datetime, tenant_id: str | None = None) -> dict:
    filtros = [RegistroUsoIa.criado_em >= inicio, RegistroUsoIa.criado_em < fim]
    if tenant_id is not None:
        filtros.append(RegistroUsoIa.tenant_id == tenant_id)

    total = db.query(
        func.count(RegistroUsoIa.id), func.sum(RegistroUsoIa.custo_usd), func.sum(RegistroUsoIa.tokens_entrada),
        func.sum(RegistroUsoIa.tokens_saida), func.sum(RegistroUsoIa.tokens_cache_leitura), func.sum(RegistroUsoIa.tokens_cache_escrita),
        func.sum(RegistroUsoIa.creditos_consumidos), func.count(func.distinct(RegistroUsoIa.usuario_id)),
        func.count(func.distinct(RegistroUsoIa.tenant_id)),
    ).filter(*filtros).one()
    chamadas, custo, entrada, saida, cache_leitura, cache_escrita, creditos_total, usuarios, tenants = total
    custo_total = _d(custo)
    sem_preco = db.query(func.count(RegistroUsoIa.id)).filter(*filtros, RegistroUsoIa.status == "sucesso", RegistroUsoIa.custo_usd.is_(None)).scalar()
    por_status = dict(db.query(RegistroUsoIa.status, func.count(RegistroUsoIa.id)).filter(*filtros).group_by(RegistroUsoIa.status).all())

    tokens_entrada_totais = int(entrada or 0) + int(cache_leitura or 0) + int(cache_escrita or 0)
    filtros_negocio = [Negocio.criado_em >= inicio, Negocio.criado_em < fim] + ([Negocio.tenant_id == tenant_id] if tenant_id else [])
    oportunidades = db.query(func.count(Negocio.id)).filter(*filtros_negocio).scalar() or 0
    filtros_reuniao = [Reuniao.criado_em >= inicio, Reuniao.criado_em < fim] + ([Reuniao.tenant_id == tenant_id] if tenant_id else [])
    reunioes = db.query(func.count(Reuniao.id)).filter(*filtros_reuniao).scalar() or 0
    custo_reunioes = _d(db.query(func.sum(RegistroUsoIa.custo_usd)).filter(*filtros, RegistroUsoIa.feature.in_(["predator.resumo_reuniao", "crm.meeting_brief"])).scalar())
    custo_oportunidades = _d(db.query(func.sum(RegistroUsoIa.custo_usd)).filter(*filtros, RegistroUsoIa.entidade_tipo == "negocio").scalar())

    receita_ganha = _d(
        db.query(func.sum(Negocio.valor)).join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(EstagioFunil.tipo == "ganho", Negocio.ganho_em >= inicio, Negocio.ganho_em < fim,
                *([Negocio.tenant_id == tenant_id] if tenant_id else []))
        .scalar()
    )
    cambio = settings.finops_cambio_usd_brl
    politica = creditos.politica_vigente(db)

    return {
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "politica_creditos": politica.status if politica else None,
        "totais": {
            "chamadas": chamadas or 0,
            "por_status": por_status,
            "custo_usd": custo_total,
            "chamadas_sem_preco": sem_preco or 0,
            "tokens_entrada": int(entrada or 0),
            "tokens_saida": int(saida or 0),
            "tokens_cache_leitura": int(cache_leitura or 0),
            "tokens_cache_escrita": int(cache_escrita or 0),
            "cache_ratio": round(int(cache_leitura or 0) / tokens_entrada_totais, 4) if tokens_entrada_totais else None,
            "creditos_consumidos": _d(creditos_total),
        },
        "unitarios": {
            "custo_por_usuario_ativo_usd": round(custo_total / usuarios, 6) if usuarios else None,
            "custo_por_tenant_usd": round(custo_total / tenants, 6) if tenants else None,
            "custo_por_oportunidade_usd": round(custo_oportunidades / oportunidades, 6) if oportunidades else None,
            "custo_por_reuniao_usd": round(custo_reunioes / reunioes, 6) if reunioes else None,
            "custo_por_bid_usd": None,
            "custo_por_processo_compra_usd": None,
            "custo_ia_sobre_receita_ganha": round(custo_total * cambio / receita_ganha, 6) if cambio and receita_ganha else None,
        },
        "receita_ia": None,
        "lucro_bruto_ia": None,
        "margem_bruta_ia": None,
        "indisponivel": {
            "receita_ia": "preço do crédito ao cliente ainda não definido (política de créditos e Fases 14/15)",
            "custo_por_bid_usd": "módulo Bid Intelligence ainda não existe (Fase 9)",
            "custo_por_processo_compra_usd": "módulo Public Procurement ainda não existe (Fase 10)",
            "custo_ia_sobre_receita_ganha": None if cambio else "defina FINOPS_CAMBIO_USD_BRL (custo em USD, receita em BRL)",
        },
        "por_tenant": _agrupar(db, RegistroUsoIa.tenant_id, filtros) if tenant_id is None else [],
        "por_modulo": _agrupar(db, RegistroUsoIa.modulo, filtros),
        "por_agente": _agrupar(db, RegistroUsoIa.agente, filtros),
        "por_feature": _agrupar(db, RegistroUsoIa.feature, filtros),
        "por_provider": _agrupar(db, RegistroUsoIa.provider, filtros),
        "por_modelo": _agrupar(db, RegistroUsoIa.model, filtros),
    }
