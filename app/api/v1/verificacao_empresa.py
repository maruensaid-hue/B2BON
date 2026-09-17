from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.verificacao_empresa import (
    RevisarVerificacaoRequestSchema,
    SolicitarVerificacaoRequestSchema,
    VerificacaoEmpresaSchema,
)
from app.services import verificacao_empresa_service
from app.services.errors import NaoAutorizado

router = APIRouter(prefix="/verificacao-empresa", tags=["verificacao-empresa"])


@router.post("", response_model=VerificacaoEmpresaSchema, status_code=201)
def solicitar_verificacao(
    dados: SolicitarVerificacaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> VerificacaoEmpresaSchema:
    """Company Claim/Verification (master prompt §37) — o próprio tenant
    solicita, sinais automáticos são calculados, mas quem decide de
    verdade é um super_admin em `/pendentes` + `/revisar`."""
    return verificacao_empresa_service.solicitar(db, tenant_id, ator_id, dados.email_verificacao)


@router.get("/pendentes", response_model=list[VerificacaoEmpresaSchema])
def listar_pendentes(
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[VerificacaoEmpresaSchema]:
    if usuario.papel != "super_admin":
        raise NaoAutorizado("Só o super_admin pode revisar solicitações de verificação.")
    return verificacao_empresa_service.listar_pendentes(db)


@router.post("/{verificacao_id}/revisar", response_model=VerificacaoEmpresaSchema)
def revisar_verificacao(
    verificacao_id: int,
    dados: RevisarVerificacaoRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> VerificacaoEmpresaSchema:
    if usuario.papel != "super_admin":
        raise NaoAutorizado("Só o super_admin pode revisar solicitações de verificação.")
    return verificacao_empresa_service.revisar(db, ator_id, verificacao_id, dados.aprovar, dados.motivo_rejeicao)
