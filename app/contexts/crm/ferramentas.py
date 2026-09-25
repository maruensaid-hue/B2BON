"""Ferramentas do CRM para o B2B ON Intelligence Agent (Fase 12)."""

from app.contexts.shared.ferramentas import FerramentaExecutavel, registrar
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio


def _listar(db, ctx, parametros: dict) -> dict:
    linhas = (
        db.query(Negocio, EstagioFunil)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Negocio.tenant_id == ctx.tenant_id, EstagioFunil.tipo == "aberto")
        .order_by(Negocio.valor.desc())
        .limit(15)
        .all()
    )
    itens = [{"negocio_id": n.id, "nome": n.nome, "valor": n.valor, "probabilidade": n.probabilidade, "estagio": e.nome} for n, e in linhas]
    return {"resumo": f"{len(itens)} negócio(s) em aberto, do maior para o menor valor.", "itens": itens}


registrar(FerramentaExecutavel(
    "crm.listar_oportunidades", agente="pipeline_agent", lado="SELL",
    palavras_chave=("negócios em aberto", "pipeline", "oportunidades abertas", "funil de vendas"),
    executar=_listar, exemplo="Quais negócios estão em aberto no pipeline?",
))
registrar(FerramentaExecutavel(
    "crm.mover_estagio", agente="pipeline_agent", lado="SELL",
    palavras_chave=("mover estágio", "avançar negócio", "mudar estágio", "marcar como ganho"),
))
