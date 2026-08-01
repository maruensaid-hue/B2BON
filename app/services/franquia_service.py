from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.conta_franquia_consumo import ContaFranquiaConsumo
from app.providers.plan_limits.base import PlanLimitsProvider
from app.services import auditoria_service
from app.services.errors import RegraNegocioViolada


def _ano_mes_atual() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _usado_no_ciclo(db: Session, tenant_id: str, ano_mes: str) -> int:
    return (
        db.query(ContaFranquiaConsumo)
        .filter_by(tenant_id=tenant_id, ano_mes=ano_mes)
        .count()
    )


def obter_franquia(db: Session, tenant_id: str, plan_limits: PlanLimitsProvider) -> dict:
    """Contador visível de franquia (E2-H1): limite vem do núcleo via
    `PlanLimitsProvider`; usado/restante são responsabilidade do PREDATOR."""
    limite = plan_limits.obter_franquia_contas_mes(tenant_id)
    usado = _usado_no_ciclo(db, tenant_id, _ano_mes_atual())
    return {"limite": limite, "usado": usado, "restante": max(limite - usado, 0)}


def consumir_para_ativacao(
    db: Session,
    tenant_id: str,
    ator_id: str | None,
    conta_ids: list[int],
    plan_limits: PlanLimitsProvider,
) -> dict:
    """Consome franquia no momento em que contas entram numa cadência ativada.

    Gerar, avaliar e descartar listas nunca chegam aqui. Idempotente por
    tenant+conta+ano_mes: reincluir a mesma conta na mesma janela mensal não
    consome de novo. Se as contas *novas* do lote excederiam o limite, a
    ativação inteira é bloqueada (nada é consumido) — cadências já ativas não
    são afetadas, porque esta função só roda no instante da ativação.

    É o gancho que o E3 (Onda 2, "ativar cadência") vai chamar; nesta onda
    não há endpoint HTTP para isto — é exercitado direto no serviço.
    """
    ano_mes = _ano_mes_atual()
    limite = plan_limits.obter_franquia_contas_mes(tenant_id)
    usado_atual = _usado_no_ciclo(db, tenant_id, ano_mes)

    ja_consumidas = {
        conta_id
        for (conta_id,) in db.query(ContaFranquiaConsumo.conta_id)
        .filter_by(tenant_id=tenant_id, ano_mes=ano_mes)
        .filter(ContaFranquiaConsumo.conta_id.in_(conta_ids))
        .all()
    }
    novas = [conta_id for conta_id in conta_ids if conta_id not in ja_consumidas]

    if usado_atual + len(novas) > limite:
        raise RegraNegocioViolada(
            "Franquia mensal de contas esgotada. Novas ativações estão bloqueadas até o "
            "próximo ciclo; cadências já ativas continuam normalmente."
        )

    agora = datetime.now(UTC)
    for conta_id in novas:
        db.add(
            ContaFranquiaConsumo(
                tenant_id=tenant_id, conta_id=conta_id, ano_mes=ano_mes, consumido_em=agora
            )
        )

    auditoria_service.registrar(
        db,
        tenant_id,
        "franquia_consumida",
        "conta_franquia_consumo",
        0,
        ator_id,
        {"contas_novas": novas, "contas_ja_consumidas": sorted(ja_consumidas)},
    )
    db.commit()

    return obter_franquia(db, tenant_id, plan_limits)
