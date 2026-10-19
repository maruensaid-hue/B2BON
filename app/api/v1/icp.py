from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.icp import ICPCreateSchema, ICPPerformanceItemSchema, ICPSchema
from app.services import icp_service

router = APIRouter(prefix="/icp", tags=["icp"])


@router.post("", response_model=ICPSchema, status_code=201)
def criar_icp(
    dados: ICPCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ICPSchema:
    return icp_service.criar(db, tenant_id, ator_id, dados)


@router.get("", response_model=list[ICPSchema])
def listar_icp(
    apenas_ativos: bool = False,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ICPSchema]:
    restrito = usuario.papel == "user"
    return icp_service.listar(db, tenant_id, apenas_ativos, usuario.id, restrito)


@router.get("/performance", response_model=list[ICPPerformanceItemSchema])
def performance_icp(
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ICPPerformanceItemSchema]:
    return icp_service.performance(db, tenant_id, usuario.id, usuario.papel == "user")


@router.get("/grupo/{grupo_id}", response_model=list[ICPSchema])
def historico_icp(
    grupo_id: str,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ICPSchema]:
    resultado = icp_service.historico(db, tenant_id, grupo_id)
    if usuario.papel == "user":
        resultado = [icp for icp in resultado if icp.criador_usuario_id == usuario.id]
    return resultado


@router.get("/{icp_id}", response_model=ICPSchema)
def obter_icp(
    icp_id: int,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ICPSchema:
    return icp_service.obter(db, tenant_id, icp_id, usuario.id, usuario.papel == "user")


@router.put("/{icp_id}", response_model=ICPSchema)
def nova_versao_icp(
    icp_id: int,
    dados: ICPCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ICPSchema:
    icp_service.obter(db, tenant_id, icp_id, usuario.id, usuario.papel == "user")
    return icp_service.nova_versao(db, tenant_id, ator_id, icp_id, dados)


@router.delete("/{icp_id}", status_code=204)
def excluir_icp(
    icp_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> None:
    icp_service.obter(db, tenant_id, icp_id, usuario.id, usuario.papel == "user")
    icp_service.excluir(db, tenant_id, ator_id, icp_id)


@router.post("/{icp_id}/clonar", response_model=ICPSchema, status_code=201)
def clonar_icp(
    icp_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ICPSchema:
    icp_service.obter(db, tenant_id, icp_id, usuario.id, usuario.papel == "user")
    return icp_service.clonar(db, tenant_id, ator_id, icp_id)
