"""Leituras para o painel: sempre filtradas por tenant. O orçamento global e a fila de reconciliação cruzam tenants e só saem em funções
administrativas (`visao_administrativa`), que a API restringe a super_admin."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import ledger
from app.contexts.enriquecimento.config import ConfigResolvida, agora_utc, config_vigente, periodo_de
from app.contexts.enriquecimento.pesquisa import Solicitante, itens_de
from app.models.conta import Conta
from app.models.enriquecimento_creditos import (
    EnriquecimentoMovimento,
    PesquisaDecisores,
    PesquisaDecisoresEmpresa,
    PesquisaDecisoresTransicao,
)


def serializar_pesquisa(db: Session, pesquisa: PesquisaDecisores, *, com_itens: bool = False, com_transicoes: bool = False) -> dict:
    dados = {
        "id": pesquisa.id, "estado": pesquisa.estado, "provedor": pesquisa.provedor, "decisores_por_empresa": pesquisa.decisores_por_empresa,
        "origem_decisores": pesquisa.origem_decisores, "total_empresas": pesquisa.total_empresas, "total_maximo": pesquisa.total_maximo,
        "creditos_reservados": pesquisa.creditos_reservados, "creditos_consumidos": pesquisa.creditos_consumidos,
        "requer_reconciliacao": pesquisa.requer_reconciliacao, "selecao_hash": pesquisa.selecao_hash,
        "previa_expira_em": pesquisa.previa_expira_em, "estimativa": pesquisa.estimativa, "motivo": pesquisa.motivo,
        "config": {"origem": pesquisa.config_origem, "versao": pesquisa.config_versao},
        "criado_em": pesquisa.criado_em, "confirmada_em": pesquisa.confirmada_em, "usuario_id": pesquisa.usuario_id,
    }
    if com_itens:
        itens = itens_de(db, pesquisa.id)
        nomes = {c.id: (c.nome_fantasia or c.nome) for c in db.query(Conta).filter(Conta.tenant_id == pesquisa.tenant_id,
                                                                                   Conta.id.in_([i.conta_id for i in itens] or [0])).all()}
        dados["itens"] = [{
            "id": i.id, "conta_id": i.conta_id, "conta_nome": nomes.get(i.conta_id), "estado": i.estado, "motivo": i.motivo,
            "decisores_existentes": i.decisores_existentes, "decisores_solicitados": i.decisores_solicitados,
            "decisores_retornados": i.decisores_retornados, "creditos_reservados": i.creditos_reservados,
            "creditos_consumidos": i.creditos_consumidos, "tentativas": i.tentativas,
        } for i in itens]
    if com_transicoes:
        transicoes = db.query(PesquisaDecisoresTransicao).filter_by(pesquisa_id=pesquisa.id).order_by(PesquisaDecisoresTransicao.id).all()
        dados["transicoes"] = [{"item_id": t.item_id, "de": t.estado_anterior, "para": t.estado_novo, "motivo": t.motivo, "em": t.criado_em}
                               for t in transicoes]
    return dados


def _resumo_config(config: ConfigResolvida | None, motivo: str | None) -> dict:
    if config is None:
        return {"disponivel": False, "motivo": motivo, "orientacao": "Fale com o comercial para liberar a pesquisa de decisores no seu plano."}
    return {
        "disponivel": config.utilizavel, "origem": config.origem, "versao": config.versao, "faltando": list(config.faltando),
        "franquia_creditos": config.franquia_creditos, "periodicidade": config.periodicidade,
        "decisores_por_empresa_padrao": config.decisores_por_empresa_padrao, "decisores_por_empresa_max": config.decisores_por_empresa_max,
        "itens_por_lote_max": config.itens_por_lote_max, "limite_periodo_creditos": config.limite_periodo_creditos,
        "orientacao": None if config.utilizavel else "Configuração incompleta: fale com o comercial.",
    }


def painel_tenant(db: Session, solicitante: Solicitante, agora: datetime | None = None) -> dict:
    """Números do tenant: franquia, disponível/reservado/consumido/expirado, uso no período e pesquisas por estado. Nada de outro tenant,
    nada do orçamento global."""
    agora = agora or agora_utc()
    tenant_id = solicitante.tenant_id
    config, motivo = config_vigente(db, tenant_id)
    ledger.preparar(db, tenant_id, config, agora)
    db.commit()
    periodo = periodo_de(agora)

    def _soma_tipo(tipo: str, coluna, so_periodo: bool = True) -> int:
        filtros = [EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo == tipo]
        if so_periodo:
            filtros.append(EnriquecimentoMovimento.periodo == periodo)
        return int(db.query(func.coalesce(func.sum(coluna), 0)).filter(*filtros).scalar() or 0)

    consulta = db.query(PesquisaDecisores.estado, func.count(PesquisaDecisores.id)).filter(PesquisaDecisores.tenant_id == tenant_id)
    if not solicitante.gestor:
        consulta = consulta.filter(PesquisaDecisores.usuario_id == solicitante.id)
    por_estado = {estado: total for estado, total in consulta.group_by(PesquisaDecisores.estado).all()}
    fechadas = db.query(func.coalesce(func.sum(PesquisaDecisores.total_maximo), 0), func.coalesce(func.sum(PesquisaDecisores.creditos_consumidos), 0)).filter(
        PesquisaDecisores.tenant_id == tenant_id, PesquisaDecisores.estado.in_(("concluida", "parcial", "reconciliada")))
    if not solicitante.gestor:
        fechadas = fechadas.filter(PesquisaDecisores.usuario_id == solicitante.id)
    estimado, consumido_pesquisas = fechadas.one()

    disponivel, retido = ledger.disponivel(db, tenant_id), ledger.reservado(db, tenant_id)
    consumido_periodo = ledger.consumo_liquido(db, tenant_id, periodo)
    alertas = []
    if config is None or not config.utilizavel:
        alertas.append({"codigo": "config_indisponivel", "mensagem": "A pesquisa de decisores não está liberada no seu plano."})
    if disponivel <= 0 and config is not None and config.utilizavel:
        alertas.append({"codigo": "sem_saldo", "mensagem": "Não há créditos de enriquecimento disponíveis."})
    if config is not None and config.limite_periodo_creditos is not None and consumido_periodo + retido >= config.limite_periodo_creditos:
        alertas.append({"codigo": "limite_periodo_atingido", "mensagem": "O limite de créditos do período foi atingido."})
    if por_estado.get("em_processamento"):
        alertas.append({"codigo": "aguardando_reconciliacao", "mensagem": "Há pesquisa aguardando reconciliação com o provedor."})
    return {
        "periodo": periodo, "plano": _resumo_config(config, motivo),
        "creditos": {
            "disponivel": disponivel, "reservado": retido, "saldo": ledger.saldo(db, tenant_id),
            "consumido_no_periodo": consumido_periodo,
            "expirado_no_periodo": -int(db.query(func.coalesce(func.sum(EnriquecimentoMovimento.delta_saldo), 0)).filter(
                EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo == "EXPIRACAO",
                EnriquecimentoMovimento.periodo == periodo).scalar() or 0),
            "concedido_no_periodo": _soma_tipo("CONCESSAO", EnriquecimentoMovimento.delta_saldo) + _soma_tipo("RENOVACAO", EnriquecimentoMovimento.delta_saldo),
        },
        "pesquisas_por_estado": por_estado,
        "estimado_vs_reconciliado": {"estimado_maximo": int(estimado), "consumido": int(consumido_pesquisas)},
        "alertas": alertas,
    }


def listar_pesquisas(db: Session, solicitante: Solicitante, estado: str | None = None, limite: int = 50, offset: int = 0) -> list[dict]:
    consulta = db.query(PesquisaDecisores).filter(PesquisaDecisores.tenant_id == solicitante.tenant_id)
    if not solicitante.gestor:
        consulta = consulta.filter(PesquisaDecisores.usuario_id == solicitante.id)
    if estado:
        consulta = consulta.filter(PesquisaDecisores.estado == estado)
    pesquisas = consulta.order_by(PesquisaDecisores.criado_em.desc(), PesquisaDecisores.id.desc()).limit(min(max(limite, 1), 200)).offset(max(offset, 0)).all()
    return [serializar_pesquisa(db, p) for p in pesquisas]


def listar_movimentacoes(db: Session, tenant_id: str, *, tipo: str | None = None, pesquisa_id: str | None = None, desde: datetime | None = None,
                         ate: datetime | None = None, limite: int = 100, offset: int = 0) -> list[dict]:
    consulta = db.query(EnriquecimentoMovimento).filter(EnriquecimentoMovimento.tenant_id == tenant_id)
    if tipo:
        consulta = consulta.filter(EnriquecimentoMovimento.tipo == tipo)
    if pesquisa_id:
        consulta = consulta.filter(EnriquecimentoMovimento.pesquisa_id == pesquisa_id)
    if desde:
        consulta = consulta.filter(EnriquecimentoMovimento.criado_em >= desde)
    if ate:
        consulta = consulta.filter(EnriquecimentoMovimento.criado_em <= ate)
    linhas = consulta.order_by(EnriquecimentoMovimento.id.desc()).limit(min(max(limite, 1), 500)).offset(max(offset, 0)).all()
    return [{
        "id": m.id, "tipo": m.tipo, "delta_saldo": m.delta_saldo, "delta_reservado": m.delta_reservado, "disponivel_apos": m.disponivel_apos,
        "pesquisa_id": m.pesquisa_id, "origem": m.origem, "motivo": m.motivo, "expira_em": m.expira_em, "criado_em": m.criado_em,
    } for m in linhas]


def visao_administrativa(db: Session, provedor: str, agora: datetime | None = None) -> dict:
    """Só super_admin: uso do orçamento global do provedor (todos os tenants) e pesquisas que precisam de reconciliação."""
    agora = agora or agora_utc()
    pendentes = (
        db.query(PesquisaDecisores).filter(PesquisaDecisores.requer_reconciliacao.is_(True))
        .order_by(PesquisaDecisores.criado_em).limit(200).all()
    )
    ambiguos = {
        pesquisa_id: total for pesquisa_id, total in db.query(PesquisaDecisoresEmpresa.pesquisa_id, func.count(PesquisaDecisoresEmpresa.id))
        .filter(PesquisaDecisoresEmpresa.estado == "ambiguo").group_by(PesquisaDecisoresEmpresa.pesquisa_id).all()
    }
    return {
        "orcamento_global": ledger.situacao_global(db, provedor, agora),
        "pendentes_reconciliacao": [{
            "pesquisa_id": p.id, "tenant_id": p.tenant_id, "estado": p.estado, "empresas_ambiguas": ambiguos.get(p.id, 0),
            "creditos_reservados": p.creditos_reservados, "criado_em": p.criado_em,
        } for p in pendentes],
    }
