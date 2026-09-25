"""Ferramentas do MAP para o B2B ON Intelligence Agent (Fase 12)."""

from app.contexts.shared.ferramentas import FerramentaExecutavel, Parametro, registrar
from app.contexts.map import saude
from app.models.conta import Conta
from app.services.errors import NaoEncontrado


def _saude(db, ctx, parametros: dict) -> dict:
    conta = db.query(Conta).filter_by(id=parametros["conta_id"], tenant_id=ctx.tenant_id).one_or_none()
    if conta is None:
        raise NaoEncontrado(f"Conta {parametros['conta_id']} não encontrada")
    risco = saude.score_risco_conta(db, conta)
    return {"resumo": f"Risco de churn {risco['classificacao']} (score {risco['score']}).", "risco": risco}


registrar(FerramentaExecutavel(
    "map.saude_conta", agente="remediation_agent", lado="SELL",
    palavras_chave=("risco de churn", "saúde da conta", "cliente em risco", "churn"),
    parametros=(Parametro("conta_id", r"conta\s*#?\s*(\d+)"),), executar=_saude, exemplo="Qual o risco de churn da conta 12?",
))
