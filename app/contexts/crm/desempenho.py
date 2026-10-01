"""Leituras agregadas de desempenho comercial do CRM interno para o MAP Performance (D-080).

Cada função faz um número fixo de consultas agrupadas por vendedor (nunca uma por representante nem uma por negócio):
o painel da equipe custa o mesmo número de queries que o individual. Só ações feitas por uma pessoa contam
(`Atividade.usuario_id` preenchido) — disparos automáticos de cadência/campanha não inflam a atividade.
"""

from datetime import datetime

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session

from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.proposta_negocio import PropostaNegocio
from app.models.reuniao import Reuniao

CAMPOS = ("contas_trabalhadas", "primeiros_toques", "acoes_comerciais", "follow_ups", "contatos_efetivos", "reunioes",
          "oportunidades_qualificadas", "propostas", "fechamentos", "valor_fechado")


def _zeros(usuario_ids: list[int]) -> dict[int, dict]:
    return {u: dict.fromkeys(CAMPOS, 0) for u in usuario_ids}


def atividade_comercial(db: Session, tenant_id: str, usuario_ids: list[int], inicio: datetime, fim: datetime,
                        definicoes: dict) -> dict[int, dict]:
    """Funil de atividade no período [inicio, fim) por vendedor (7 consultas agrupadas)."""
    resultado = _zeros(usuario_ids)
    if not usuario_ids:
        return resultado
    tipos_acao = definicoes["tipos_acao_comercial"]
    base = (Atividade.tenant_id == tenant_id, Atividade.usuario_id.in_(usuario_ids), Atividade.conta_id.isnot(None))
    # 1º toque de cada vendedor em cada conta: "conta trabalhada" só quando o 1º toque cai no período e a conta tem
    # ICP validado e uma persona/contato alvo cadastrado.
    primeiro = (db.query(Atividade.usuario_id.label("usuario_id"), Atividade.conta_id.label("conta_id"),
                         func.min(Atividade.criado_em).label("primeiro_em"))
                .filter(*base, Atividade.tipo.in_(tipos_acao)).group_by(Atividade.usuario_id, Atividade.conta_id).subquery())
    no_periodo = and_(primeiro.c.primeiro_em >= inicio, primeiro.c.primeiro_em < fim)
    icp_validado = or_(Conta.icp_id.isnot(None), Conta.score_aderencia >= definicoes["score_icp_minimo"])
    com_persona = exists().where(Decisor.conta_id == Conta.id, Decisor.tenant_id == tenant_id)
    for usuario_id, toques, trabalhadas in (
        db.query(primeiro.c.usuario_id, func.count(), func.sum(case((and_(icp_validado, com_persona), 1), else_=0)))
        .join(Conta, Conta.id == primeiro.c.conta_id).filter(no_periodo).group_by(primeiro.c.usuario_id).all()
    ):
        resultado[usuario_id].update(primeiros_toques=toques, contas_trabalhadas=int(trabalhadas or 0))
    periodo = (Atividade.criado_em >= inicio, Atividade.criado_em < fim)
    for usuario_id, acoes in (db.query(Atividade.usuario_id, func.count()).filter(*base, *periodo, Atividade.tipo.in_(tipos_acao))
                              .group_by(Atividade.usuario_id).all()):
        resultado[usuario_id]["acoes_comerciais"] = acoes
    for usuario_id, contatos in (db.query(Atividade.usuario_id, func.count(func.distinct(Atividade.conta_id)))
                                 .filter(*base, *periodo, Atividade.tipo.in_(definicoes["tipos_contato_efetivo"]))
                                 .group_by(Atividade.usuario_id).all()):
        resultado[usuario_id]["contatos_efetivos"] = contatos
    por_texto = {str(u): u for u in usuario_ids}
    for vendedor, reunioes in (db.query(Reuniao.vendedor_id, func.count())
                               .filter(Reuniao.tenant_id == tenant_id, Reuniao.vendedor_id.in_(list(por_texto)),
                                       Reuniao.status == "realizada", Reuniao.data_hora >= inicio, Reuniao.data_hora < fim)
                               .group_by(Reuniao.vendedor_id).all()):
        resultado[por_texto[vendedor]]["reunioes"] = reunioes
    do_vendedor = (Negocio.tenant_id == tenant_id, Negocio.vendedor_usuario_id.in_(usuario_ids))
    for usuario_id, criadas in (db.query(Negocio.vendedor_usuario_id, func.count()).filter(*do_vendedor, Negocio.criado_em >= inicio,
                                                                                            Negocio.criado_em < fim)
                                .group_by(Negocio.vendedor_usuario_id).all()):
        resultado[usuario_id]["oportunidades_qualificadas"] = criadas
    for usuario_id, propostas in (db.query(Negocio.vendedor_usuario_id, func.count(func.distinct(PropostaNegocio.negocio_id)))
                                  .join(PropostaNegocio, PropostaNegocio.negocio_id == Negocio.id)
                                  .filter(*do_vendedor, PropostaNegocio.criado_em >= inicio, PropostaNegocio.criado_em < fim)
                                  .group_by(Negocio.vendedor_usuario_id).all()):
        resultado[usuario_id]["propostas"] = propostas
    for usuario_id, fechamentos, valor in (db.query(Negocio.vendedor_usuario_id, func.count(), func.coalesce(func.sum(Negocio.valor), 0))
                                           .filter(*do_vendedor, Negocio.ganho_em >= inicio, Negocio.ganho_em < fim)
                                           .group_by(Negocio.vendedor_usuario_id).all()):
        resultado[usuario_id].update(fechamentos=fechamentos, valor_fechado=float(valor))
    for linha in resultado.values():
        linha["follow_ups"] = max(linha["acoes_comerciais"] - linha["primeiros_toques"], 0)
    return resultado


def pipeline_aberto(db: Session, tenant_id: str, usuario_ids: list[int]) -> list[dict]:
    """Negócios abertos dos vendedores, com a última ação humana e se já têm proposta (1 consulta)."""
    if not usuario_ids:
        return []
    ultima = (db.query(Atividade.negocio_id.label("negocio_id"), func.max(Atividade.criado_em).label("em"))
              .filter(Atividade.tenant_id == tenant_id, Atividade.negocio_id.isnot(None), Atividade.usuario_id.isnot(None))
              .group_by(Atividade.negocio_id).subquery())
    propostas = (db.query(PropostaNegocio.negocio_id.label("negocio_id"), func.max(PropostaNegocio.criado_em).label("em"))
                 .filter(PropostaNegocio.tenant_id == tenant_id).group_by(PropostaNegocio.negocio_id).subquery())
    linhas = (db.query(Negocio.id, Negocio.nome, Negocio.vendedor_usuario_id, Negocio.conta_id, Conta.nome, Negocio.valor,
                       Negocio.probabilidade, Negocio.oferta_id, EstagioFunil.nome, EstagioFunil.ordem, Negocio.criado_em,
                       Negocio.atualizado_em, ultima.c.em, propostas.c.em, Conta.proximo_passo, Conta.proximo_passo_em)
              .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id).join(Conta, Conta.id == Negocio.conta_id)
              .outerjoin(ultima, ultima.c.negocio_id == Negocio.id).outerjoin(propostas, propostas.c.negocio_id == Negocio.id)
              .filter(Negocio.tenant_id == tenant_id, Negocio.vendedor_usuario_id.in_(usuario_ids), EstagioFunil.tipo == "aberto")
              .all())
    return [{"id": i, "nome": nome, "usuario_id": usuario, "conta_id": conta_id, "conta": conta, "valor": float(valor or 0),
             "probabilidade": prob or 0, "oferta_id": oferta, "estagio": estagio, "estagio_ordem": ordem, "criado_em": criado,
             "atualizado_em": atualizado, "ultima_acao_em": acao, "proposta_em": proposta, "proximo_passo": passo,
             "proximo_passo_em": passo_em}
            for (i, nome, usuario, conta_id, conta, valor, prob, oferta, estagio, ordem, criado, atualizado, acao, proposta, passo,
                 passo_em) in linhas]


def ganhos(db: Session, tenant_id: str, usuario_ids: list[int], desde: datetime) -> list[dict]:
    """Negócios ganhos desde a data: ciclo real (dias) por vendedor e oferta (1 consulta)."""
    if not usuario_ids:
        return []
    return [{"usuario_id": u, "oferta_id": o, "valor": float(v or 0), "dias_ciclo": max((g - c).days, 0)}
            for u, o, v, c, g in db.query(Negocio.vendedor_usuario_id, Negocio.oferta_id, Negocio.valor, Negocio.criado_em, Negocio.ganho_em)
            .filter(Negocio.tenant_id == tenant_id, Negocio.vendedor_usuario_id.in_(usuario_ids), Negocio.ganho_em >= desde).all()]
