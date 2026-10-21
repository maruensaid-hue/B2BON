"""Leituras para o painel: sempre filtradas por tenant. O orçamento global, o custo de aquisição, o markup, a margem e a fila de reconciliação
cruzam tenants (ou revelam a economia da CyberFort) e só saem em funções administrativas (`visao_administrativa`, `planos_status`), que a API
restringe a super_admin."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.contexts.enriquecimento import conciliacao, ledger, precos
from app.contexts.enriquecimento.config import (
    CAMPOS_OBRIGATORIOS_POR_MODO,
    agora_utc,
    config_vigente,
    fim_do_mes,
    motivos_de_indisponibilidade,
    orcamento_vigente,
    periodo_de,
    politica_vigente,
)
from app.contexts.enriquecimento.pesquisa import Solicitante, itens_de, uso_do_periodo
from app.models.conta import Conta
from app.models.enriquecimento_creditos import (
    EnriquecimentoConfigPlano,
    EnriquecimentoLoteCompra,
    EnriquecimentoMovimento,
    EnriquecimentoOrcamentoGlobal,
    EnriquecimentoPoliticaProvedor,
    PesquisaDecisores,
    PesquisaDecisoresEmpresa,
    PesquisaDecisoresTransicao,
)
from app.models.auditoria import AuditLog
from app.models.plano import Plano
from app.providers.contact_enrichment.base import ContactEnrichmentProvider


def serializar_pesquisa(db: Session, pesquisa: PesquisaDecisores, *, com_itens: bool = False, com_transicoes: bool = False) -> dict:
    dados = {
        "id": pesquisa.id, "estado": pesquisa.estado, "provedor": pesquisa.provedor, "decisores_por_empresa": pesquisa.decisores_por_empresa,
        "origem_decisores": pesquisa.origem_decisores, "total_empresas": pesquisa.total_empresas, "total_maximo": pesquisa.total_maximo,
        "creditos_reservados": pesquisa.creditos_reservados, "creditos_consumidos": pesquisa.creditos_consumidos,
        "provedor_reservados": pesquisa.provedor_reservados, "provedor_consumidos": pesquisa.provedor_consumidos,
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
            "creditos_consumidos": i.creditos_consumidos, "provedor_reservados": i.provedor_reservados, "provedor_medidos": i.provedor_medidos,
            "tentativas": i.tentativas,
        } for i in itens]
    if com_transicoes:
        transicoes = db.query(PesquisaDecisoresTransicao).filter_by(pesquisa_id=pesquisa.id).order_by(PesquisaDecisoresTransicao.id).all()
        dados["transicoes"] = [{"item_id": t.item_id, "de": t.estado_anterior, "para": t.estado_novo, "motivo": t.motivo, "em": t.criado_em}
                               for t in transicoes]
    return dados


def _resumo_config(config, motivo: str | None) -> dict:
    if config is None:
        return {"disponivel": False, "motivo": motivo, "orientacao": "Fale com o comercial para liberar a pesquisa de decisores no seu plano."}
    return {
        "disponivel": config.utilizavel, "origem": config.origem, "versao": config.versao, "faltando": list(config.faltando),
        "franquia_creditos": config.franquia_creditos, "periodicidade": config.periodicidade,
        "decisores_por_empresa_padrao": config.decisores_por_empresa_padrao, "decisores_por_empresa_max": config.decisores_por_empresa_max,
        "itens_por_lote_max": config.itens_por_lote_max, "limite_periodo_creditos": config.limite_periodo_creditos, "modo": config.modo,
        "limite_creditos_pesquisa": config.limite_creditos_pesquisa, "limite_pesquisas_periodo": config.limite_pesquisas_periodo,
        "limite_empresas_periodo": config.limite_empresas_periodo, "limite_contatos_periodo": config.limite_contatos_periodo,
        "orientacao": None if config.utilizavel else "Configuração incompleta: fale com o comercial.",
    }


def painel_tenant(db: Session, solicitante: Solicitante, provider: ContactEnrichmentProvider, agora: datetime | None = None) -> dict:
    """Números do tenant: franquia, disponível/reservado/consumido/expirado, uso no período, uso por fonte, pesquisas por estado e a disponibilidade
    da pesquisa Lusha com o MOTIVO quando indisponível. Nada de outro tenant, nada do orçamento global, do custo ou da margem."""
    agora = agora or agora_utc()
    tenant_id = solicitante.tenant_id
    config, motivo = config_vigente(db, tenant_id)
    ledger.preparar(db, tenant_id, config, agora)
    db.commit()
    periodo = periodo_de(agora)

    def _soma_tipo(tipo: str, coluna) -> int:
        return int(db.query(func.coalesce(func.sum(coluna), 0)).filter(
            EnriquecimentoMovimento.tenant_id == tenant_id, EnriquecimentoMovimento.tipo == tipo, EnriquecimentoMovimento.periodo == periodo).scalar() or 0)

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
    motivos = motivos_de_indisponibilidade(db, tenant_id, provider)
    alertas = []
    if motivos:
        alertas.append({"codigo": "pesquisa_lusha_indisponivel", "mensagem": "A pesquisa de decisores (Lusha) está indisponível: " + motivos[0]["mensagem"]})
    if disponivel <= 0 and config is not None and config.utilizavel:
        alertas.append({"codigo": "sem_saldo", "mensagem": "Não há créditos de enriquecimento disponíveis."})
    if config is not None and config.limite_periodo_creditos is not None and consumido_periodo + retido >= config.limite_periodo_creditos:
        alertas.append({"codigo": "limite_periodo_atingido", "mensagem": "O limite de créditos do período foi atingido."})
    if por_estado.get("em_processamento"):
        alertas.append({"codigo": "aguardando_reconciliacao", "mensagem": "Há pesquisa aguardando reconciliação com o provedor."})
    return {
        "periodo": periodo, "plano": _resumo_config(config, motivo),
        "lusha": {"disponivel": not motivos, "motivos": motivos},
        "categorias": {
            "ia": "Os créditos de IA (incluindo a análise de sites) são contabilizados à parte, no módulo AI Credits.",
            "enriquecimento": "Créditos de enriquecimento (pesquisa de decisores no provedor pago): esta página.",
        },
        "creditos": {
            "disponivel": disponivel, "reservado": retido, "saldo": ledger.saldo(db, tenant_id),
            "consumido_no_periodo": consumido_periodo,
            "expirado_no_periodo": -_soma_tipo("EXPIRACAO", EnriquecimentoMovimento.delta_saldo),
            "concedido_no_periodo": _soma_tipo("CONCESSAO", EnriquecimentoMovimento.delta_saldo) + _soma_tipo("RENOVACAO", EnriquecimentoMovimento.delta_saldo),
            "comprado_no_periodo": _soma_tipo("COMPRA", EnriquecimentoMovimento.delta_saldo),
        },
        # Franquia do mês e saldo adicional (pacotes comprados) são grandezas separadas; ambas vencem no fim do mês de Brasília e não acumulam.
        # O adicional NÃO aumenta nenhum limite do plano (decisores por empresa, créditos por pesquisa).
        "composicao": {**ledger.composicao(db, tenant_id, agora), "expira_em": fim_do_mes(agora).isoformat(), "acumula": False},
        "uso_no_periodo": uso_do_periodo(db, tenant_id, agora),
        "compra_adicional": {"disponivel": not motivos, "motivos": motivos},
        "uso_por_fonte": ledger.uso_por_fonte(db, tenant_id, periodo),
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
    """Extrato do tenant. Não inclui custo de aquisição, markup nem margem (informação da CyberFort)."""
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
        "creditos_provedor": m.provedor_delta_consumido or None, "fonte": m.fonte, "pesquisa_id": m.pesquisa_id, "origem": m.origem,
        "motivo": m.motivo, "expira_em": m.expira_em, "criado_em": m.criado_em,
    } for m in linhas]


def _politica_admin(db: Session, provedor: str) -> dict | None:
    politica, motivo = politica_vigente(db, provedor)
    if politica is None:
        return {"vigente": False, "motivo": motivo}
    return {
        "vigente": True, "versao": politica.versao, "utilizavel": politica.utilizavel, "faltando": list(politica.faltando),
        "creditos_busca_por_resultado": politica.creditos_busca_por_resultado, "creditos_email": politica.creditos_email,
        "creditos_telefone": politica.creditos_telefone, "revelar": politica.revelar, "tamanho_pagina_busca": politica.tamanho_pagina_busca,
        "creditos_cliente_por_credito_provedor": politica.creditos_cliente_por_credito_provedor,
        "custo_unitario_brl": str(politica.custo_unitario_brl), "markup_percentual": str(politica.markup_percentual),
        "preco_unitario_brl": str(politica.preco_unitario_brl),
        "preco_unitario_exibicao": str(precos.exibir(politica.preco_unitario_brl, politica.casas_exibicao)),
        "margem_bruta_percentual": str(precos.margem_bruta_percentual(politica.markup_percentual)),
    }


def visao_administrativa(db: Session, provedor: str, agora: datetime | None = None) -> dict:
    """Só super_admin: orçamento global do provedor (todos os tenants), política (tarifas, custo, markup, preço, margem), resultado financeiro,
    lotes de compra, leituras de uso do provedor, aprovações pendentes e pesquisas que precisam de reconciliação."""
    agora = agora or agora_utc()
    pendentes = (
        db.query(PesquisaDecisores).filter(PesquisaDecisores.requer_reconciliacao.is_(True)).order_by(PesquisaDecisores.criado_em).limit(200).all()
    )
    ambiguos = {
        pesquisa_id: total for pesquisa_id, total in db.query(PesquisaDecisoresEmpresa.pesquisa_id, func.count(PesquisaDecisoresEmpresa.id))
        .filter(PesquisaDecisoresEmpresa.estado == "ambiguo").group_by(PesquisaDecisoresEmpresa.pesquisa_id).all()
    }
    lotes = db.query(EnriquecimentoLoteCompra).filter_by(provedor=provedor).order_by(EnriquecimentoLoteCompra.id).all()
    pendentes_aprovacao = {
        "configs": db.query(EnriquecimentoConfigPlano).filter(EnriquecimentoConfigPlano.aprovado_em.is_(None)).count(),
        "politicas": db.query(EnriquecimentoPoliticaProvedor).filter(EnriquecimentoPoliticaProvedor.provedor == provedor,
                                                                     EnriquecimentoPoliticaProvedor.aprovado_em.is_(None)).count(),
        "orcamentos": db.query(EnriquecimentoOrcamentoGlobal).filter(EnriquecimentoOrcamentoGlobal.provedor == provedor,
                                                                     EnriquecimentoOrcamentoGlobal.aprovado_em.is_(None)).count(),
    }
    resultado_mes = ledger.resultado_financeiro(db, provedor, periodo_de(agora))
    resultado_total = ledger.resultado_financeiro(db, provedor)
    return {
        "orcamento_global": ledger.situacao_global(db, provedor, agora),
        "orcamento_pendente_aprovacao": orcamento_vigente(db, provedor).pendente_aprovacao,
        "politica": _politica_admin(db, provedor),
        "resultado_financeiro": {
            "mes": {k: (str(v) if v is not None else None) for k, v in resultado_mes.items()},
            "total": {k: (str(v) if v is not None else None) for k, v in resultado_total.items()},
        },
        "lotes_compra": [{
            "id": lote.id, "referencia": lote.referencia, "quantidade_creditos": lote.quantidade_creditos, "custo_total_brl": str(lote.custo_total_brl),
            "custo_unitario_brl": str(lote.custo_unitario_brl), "comprado_em": lote.comprado_em,
        } for lote in lotes],
        "leituras_de_uso": conciliacao.listar(db, provedor, 10),
        "aprovacoes_pendentes": pendentes_aprovacao,
        "pendentes_reconciliacao": [{
            "pesquisa_id": p.id, "tenant_id": p.tenant_id, "estado": p.estado, "empresas_ambiguas": ambiguos.get(p.id, 0),
            "creditos_provedor_reservados": p.provedor_reservados, "criado_em": p.criado_em,
        } for p in pendentes],
    }


def planos_status(db: Session) -> list[dict]:
    """Por plano: a configuração de enriquecimento está aprovada, pendente ou ausente? (É o que decide se a Lusha está liberada para os
    clientes do plano.) Só super_admin."""
    saida = []
    for plano in db.query(Plano).order_by(Plano.id).all():
        linhas = db.query(EnriquecimentoConfigPlano).filter(EnriquecimentoConfigPlano.plano_id == plano.id).order_by(
            EnriquecimentoConfigPlano.versao.desc()).all()
        aprovada = next((c for c in linhas if c.aprovado_em is not None and c.valido_ate is None), None)
        pendente = next((c for c in linhas if c.aprovado_em is None), None)
        saida.append({
            "plano_id": plano.id, "plano": plano.nome,
            "situacao": "aprovada" if aprovada else ("pendente_aprovacao" if pendente else "sem_configuracao"),
            "versao_aprovada": aprovada.versao if aprovada else None, "versao_pendente": pendente.versao if pendente else None,
            "modo": aprovada.modo if aprovada else None,
            "faltando": [campo for campo in CAMPOS_OBRIGATORIOS_POR_MODO[(aprovada.modo or "franquia_fixa")]
                         if aprovada is not None and getattr(aprovada, campo) is None] if aprovada is not None else [],
        })
    return saida


def auditoria_administrativa(db: Session, *, tenant_id: str | None = None, prefixo: str = "enriquecimento_", limite: int = 100, offset: int = 0) -> list[dict]:
    """Trilha de auditoria dos eventos de enriquecimento (configuração, pacotes, orçamento, política, lotes, ajustes, compras...), mais recente
    primeiro. Cruza tenants: só super_admin. `detalhes` já nasce sem segredos (nenhuma credencial passa por esses eventos)."""
    consulta = db.query(AuditLog).filter(AuditLog.evento_tipo.like(f"{prefixo}%"))
    if tenant_id:
        consulta = consulta.filter(AuditLog.tenant_id == tenant_id)
    linhas = consulta.order_by(AuditLog.id.desc()).offset(max(0, offset)).limit(max(1, min(limite, 500))).all()
    return [{"id": a.id, "tenant_id": a.tenant_id, "evento": a.evento_tipo, "entidade": a.entidade_tipo, "entidade_id": a.entidade_id,
             "ator_id": a.ator_id, "detalhes": a.detalhes, "criado_em": a.criado_em} for a in linhas]
