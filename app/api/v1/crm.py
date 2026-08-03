from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.conta import ContaSchema
from app.schemas.crm import (
    AtividadeSchema,
    CancelarClienteRequestSchema,
    CriarNegocioRequestSchema,
    CustoAquisicaoSchema,
    DashboardAtividadeSchema,
    DashboardEconomiaSchema,
    DashboardFlywheelSchema,
    DashboardFunilSchema,
    DefinirCustoAquisicaoRequestSchema,
    DefinirEstagioRequestSchema,
    EstagioFunilSchema,
    MoverEstagioRequestSchema,
    NegocioSchema,
    RegistrarAtividadeRequestSchema,
)
from app.services import crm_service

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("/estagios", response_model=list[EstagioFunilSchema])
def listar_estagios(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[EstagioFunilSchema]:
    """Funil de vendas configurável por tenant (Onda B)."""
    return crm_service.listar_estagios(db, tenant_id)


@router.put("/estagios/{estagio_id}", response_model=EstagioFunilSchema)
def definir_estagio(
    estagio_id: int,
    dados: DefinirEstagioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> EstagioFunilSchema:
    return crm_service.definir_estagio(db, tenant_id, ator_id, estagio_id, dados.nome, dados.ordem, dados.tipo)


@router.get("/negocios", response_model=list[NegocioSchema])
def listar_negocios(
    estagio_id: int | None = None,
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[NegocioSchema]:
    """O "kanban de clientes" (Onda B)."""
    return crm_service.listar_negocios(db, tenant_id, estagio_id, vendedor_usuario_id)


@router.post("/negocios", response_model=NegocioSchema, status_code=201)
def criar_negocio(
    dados: CriarNegocioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> NegocioSchema:
    return crm_service.criar_negocio(
        db,
        tenant_id,
        ator_id,
        dados.conta_id,
        dados.nome,
        dados.valor,
        dados.probabilidade,
        dados.vendedor_usuario_id,
        dados.estagio_id,
    )


@router.put("/negocios/{negocio_id}/estagio", response_model=NegocioSchema)
def mover_estagio(
    negocio_id: int,
    dados: MoverEstagioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> NegocioSchema:
    """Arrastar no kanban — ganho marca a conta como cliente, perdido grava o motivo (Onda B)."""
    return crm_service.mover_estagio(db, tenant_id, ator_id, negocio_id, dados.estagio_id, dados.motivo_perda)


@router.post("/negocios/{negocio_id}/atividades", response_model=AtividadeSchema, status_code=201)
def registrar_atividade(
    negocio_id: int,
    dados: RegistrarAtividadeRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> AtividadeSchema:
    return crm_service.registrar_atividade(db, tenant_id, ator_id, negocio_id, dados.tipo, dados.descricao)


@router.get("/negocios/{negocio_id}/atividades", response_model=list[AtividadeSchema])
def listar_atividades(
    negocio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[AtividadeSchema]:
    return crm_service.listar_atividades(db, tenant_id, negocio_id)


@router.post("/contas/{conta_id}/cancelar-cliente", response_model=ContaSchema)
def cancelar_cliente(
    conta_id: int,
    dados: CancelarClienteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    """Registra o evento de churn (Onda B)."""
    return crm_service.marcar_cliente_cancelado(db, tenant_id, ator_id, conta_id, dados.motivo)


@router.put("/custo-aquisicao", response_model=CustoAquisicaoSchema)
def definir_custo_aquisicao(
    dados: DefinirCustoAquisicaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CustoAquisicaoSchema:
    return crm_service.definir_custo_aquisicao(db, tenant_id, ator_id, dados.periodo, dados.valor)


@router.get("/dashboard/funil", response_model=DashboardFunilSchema)
def dashboard_funil(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFunilSchema:
    return DashboardFunilSchema(**crm_service.dashboard_funil(db, tenant_id, data_inicio, data_fim))


@router.get("/dashboard/atividade", response_model=DashboardAtividadeSchema)
def dashboard_atividade(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardAtividadeSchema:
    return DashboardAtividadeSchema(**crm_service.dashboard_atividade(db, tenant_id, data_inicio, data_fim))


@router.get("/dashboard/economia", response_model=DashboardEconomiaSchema)
def dashboard_economia(
    periodo: str,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardEconomiaSchema:
    """LTV, CAC e Churn do período "YYYY-MM" (Onda B)."""
    return DashboardEconomiaSchema(**crm_service.dashboard_economia(db, tenant_id, periodo))


@router.get("/dashboard/flywheel", response_model=DashboardFlywheelSchema)
def dashboard_flywheel(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFlywheelSchema:
    """CRM (novo) + PREDATOR (já existente) num único payload (Onda B)."""
    return DashboardFlywheelSchema(**crm_service.dashboard_flywheel(db, tenant_id))
