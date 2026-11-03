"""Ciclo automático de prospecção (harvey: "busca, escreve e lê respostas a cada 15 minutos"), por cadência que pediu isso.

A cada rodada, para cada cadência com `prospeccao_automatica` ligada:
1. Ativa sozinha quando todos os rascunhos novos já foram aprovados (a aprovação humana continua sendo o portão: nada sai sem ela).
2. Escolhe até `MAXIMO_CONTAS_POR_LOTE` contas do ICP da cadência que ainda não estão nela, já tiveram o site confirmado no
   enriquecimento, têm decisor e atendem aos critérios de sinais do ICP (melhor score primeiro), e gera os rascunhos delas.
   Com a fila de aprovação cheia (`LIMITE_PENDENTES`), não gera mais: escrever sem ninguém revisar só acumula.
Buscar empresas novas (pago) continua manual; ler o site das descobertas já entra sozinho na fila de enriquecimento.
"""

import logging

from sqlalchemy.orm import Session

from app.contexts.predator import contract as predator_contract
from app.llm.base import LLMProvider
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services import cadencia_service
from app.services.errors import ErroServico

logger = logging.getLogger(__name__)

LIMITE_PENDENTES = 40


def _ativar_se_tudo_aprovado(db: Session, tenant_id: str, cadencia: Cadencia, plan_limits: PlanLimitsProvider) -> str | None:
    novas = db.query(Mensagem.status).filter(
        Mensagem.tenant_id == tenant_id, Mensagem.cadencia_id == cadencia.id, Mensagem.agendado_para.is_(None)
    ).all()
    status = {s for (s,) in novas}
    if "aprovado" not in status or "aguardando_aprovacao" in status:
        return None
    try:
        cadencia_service.ativar(db, tenant_id, None, cadencia.id, plan_limits)
    except ErroServico as erro:
        db.rollback()
        return f"não ativada: {erro}"
    return "ativada"


def _contas_elegiveis(db: Session, tenant_id: str, cadencia: Cadencia, limite: int) -> list[int]:
    icp = db.query(ICP).filter_by(id=cadencia.icp_id, tenant_id=tenant_id).one_or_none()
    if icp is None:
        return []
    ja_na_cadencia = (
        db.query(Decisor.conta_id)
        .join(Mensagem, Mensagem.decisor_id == Decisor.id)
        .filter(Mensagem.tenant_id == tenant_id, Mensagem.cadencia_id == cadencia.id)
    )
    candidatas = [
        conta_id for (conta_id,) in db.query(Conta.id)
        .filter(Conta.tenant_id == tenant_id, Conta.icp_id == icp.id, Conta.status != "descartada", Conta.id.notin_(ja_na_cadencia))
        .filter(Conta.id.in_(db.query(Decisor.conta_id).filter(Decisor.tenant_id == tenant_id, Decisor.suprimido_em.is_(None))))
        .order_by(Conta.score_aderencia.desc().nullslast(), Conta.id)
        .all()
    ]
    sinais = predator_contract.sinais
    criterios = sinais.validar_criterios(icp.criterios_sinais or [])
    codigos = ["DOMINIO_CONFIRMADO", *(c["codigo"] for c in criterios)]
    por_conta = sinais.vigentes(db, tenant_id, candidatas, codigos)
    escolhidas: list[int] = []
    for conta_id in candidatas:
        da_conta = por_conta.get(conta_id, {})
        confirmado = da_conta.get("DOMINIO_CONFIRMADO")
        if confirmado is None or confirmado.valor_num != 1:
            continue  # ainda não enriquecida (ou site não é da empresa): sem fato para citar
        if sinais.avaliar(criterios, da_conta).atende:
            escolhidas.append(conta_id)
            if len(escolhidas) >= limite:
                break
    return escolhidas


def executar_para_tenant(db: Session, tenant_id: str, llm: LLMProvider, plan_limits: PlanLimitsProvider) -> dict:
    cadencias = (
        db.query(Cadencia)
        .filter(Cadencia.tenant_id == tenant_id, Cadencia.prospeccao_automatica.is_(True), Cadencia.status != "cancelada",
                Cadencia.icp_id.isnot(None))
        .order_by(Cadencia.id)
        .all()
    )
    resultado: dict[int, dict] = {}
    for cadencia in cadencias:
        item: dict = {"ativacao": _ativar_se_tudo_aprovado(db, tenant_id, cadencia, plan_limits)}
        pendentes = db.query(Mensagem.id).filter(
            Mensagem.tenant_id == tenant_id, Mensagem.cadencia_id == cadencia.id, Mensagem.status == "aguardando_aprovacao"
        ).count()
        if pendentes >= LIMITE_PENDENTES:
            item["geracao"] = f"fila de aprovação cheia ({pendentes} pendentes)"
        else:
            contas = _contas_elegiveis(db, tenant_id, cadencia, cadencia_service.MAXIMO_CONTAS_POR_LOTE)
            if contas:
                try:
                    gerado = cadencia_service.gerar_para_lote(db, tenant_id, None, cadencia.id, contas, llm, plan_limits)
                    item["geracao"] = {"contas": gerado["contas_processadas"], "mensagens": gerado["mensagens_geradas"]}
                except ErroServico as erro:
                    db.rollback()
                    item["geracao"] = f"não gerada: {erro}"
            else:
                item["geracao"] = "nenhuma conta nova elegível"
        resultado[cadencia.id] = item
    return {"cadencias": resultado}
