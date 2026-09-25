"""Contrato público do contexto CRM (Fase 1).

É por aqui, e não pelo ORM de `Negocio`/`EstagioFunil`, que outros
contextos (MAP primeiro) leem pipeline e receita do CRM interno. Um
CRM externo (Fase 13) entra pela porta do contexto consumidor
(ex.: `MapDataSource`), não por aqui.
"""

from sqlalchemy.orm import Session

from app.models.custo_aquisicao import CustoAquisicao
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio


def funil(db: Session, tenant_id: str, vendedor_usuario_id: int | None = None) -> dict:
    # Import local: `crm_service` importa o contrato do MAP, que usa este
    # módulo — no carregamento, os dois só se enxergam dentro da chamada.
    from app.services import crm_service

    return crm_service.dashboard_funil(db, tenant_id, vendedor_usuario_id)


def _valor_por_conta(db: Session, tenant_id: str, tipo_estagio: str, conta_ids: list[int] | None) -> dict[int, float]:
    query = (
        db.query(Negocio.conta_id, Negocio.valor)
        .join(EstagioFunil, Negocio.estagio_id == EstagioFunil.id)
        .filter(Negocio.tenant_id == tenant_id, EstagioFunil.tipo == tipo_estagio)
    )
    if conta_ids is not None:
        if not conta_ids:
            return {}
        query = query.filter(Negocio.conta_id.in_(conta_ids))
    totais: dict[int, float] = {}
    for conta_id, valor in query.all():
        totais[conta_id] = totais.get(conta_id, 0.0) + valor
    return totais


def valor_ganho_por_conta(db: Session, tenant_id: str, conta_ids: list[int] | None = None) -> dict[int, float]:
    return _valor_por_conta(db, tenant_id, "ganho", conta_ids)


def valor_pipeline_aberto(db: Session, tenant_id: str, conta_id: int) -> float:
    return _valor_por_conta(db, tenant_id, "aberto", [conta_id]).get(conta_id, 0.0)


def custo_aquisicao(db: Session, tenant_id: str, periodo: str) -> float | None:
    custo = db.query(CustoAquisicao).filter_by(tenant_id=tenant_id, periodo=periodo).one_or_none()
    return custo.valor if custo else None


def abrir_ou_reaproveitar_oportunidade(
    db: Session, tenant_id: str, ator_id: str | None, conta_id: int, nome: str, origem: str
) -> tuple[Negocio, bool]:
    """Network → CRM (Fase 8): reaproveita o negócio aberto da conta ou cria um."""
    from app.services import crm_service

    return crm_service.abrir_ou_reaproveitar_oportunidade(db, tenant_id, ator_id, conta_id, nome, origem)

# Fase 12: registra as ferramentas deste contexto no B2B ON Intelligence Agent.
from app.contexts.crm import ferramentas as _ferramentas  # noqa: E402, F401
