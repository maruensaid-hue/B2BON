from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.aprovacao import (
    AprovacaoFilaItemSchema,
    AprovacaoSchema,
    AprovarLoteRequestSchema,
    DefinirRegraAutoAprovacaoRequestSchema,
    EditarMensagemRequestSchema,
    RegraAutoAprovacaoSchema,
    RejeitarRequestSchema,
)
from app.schemas.mensagem import MensagemSchema
from app.services import aprovacao_service

router = APIRouter(prefix="/aprovacoes", tags=["aprovacoes"])


@router.get("", response_model=list[AprovacaoFilaItemSchema])
def listar_fila(
    canal: str | None = None,
    conta_id: int | None = None,
    cadencia_id: int | None = None,
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[AprovacaoFilaItemSchema]:
    itens = aprovacao_service.listar_fila(db, tenant_id, canal, conta_id, cadencia_id, status)
    return [AprovacaoFilaItemSchema(**item) for item in itens]


@router.post("/aprovar-lote", response_model=list[AprovacaoSchema])
def aprovar_lote(
    dados: AprovarLoteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> list[AprovacaoSchema]:
    return aprovacao_service.aprovar_lote(db, tenant_id, ator_id, dados.ids)


@router.post("/{aprovacao_id}/aprovar", response_model=AprovacaoSchema)
def aprovar(
    aprovacao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> AprovacaoSchema:
    return aprovacao_service.aprovar(db, tenant_id, ator_id, aprovacao_id)


@router.post("/{aprovacao_id}/rejeitar", response_model=AprovacaoSchema)
def rejeitar(
    aprovacao_id: int,
    dados: RejeitarRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> AprovacaoSchema:
    return aprovacao_service.rejeitar(db, tenant_id, ator_id, aprovacao_id, dados.motivo)


@router.put("/{aprovacao_id}/mensagem", response_model=MensagemSchema)
def editar_mensagem(
    aprovacao_id: int,
    dados: EditarMensagemRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MensagemSchema:
    return aprovacao_service.editar_mensagem(db, tenant_id, ator_id, aprovacao_id, dados.conteudo)


@router.get("/regras", response_model=list[RegraAutoAprovacaoSchema])
def listar_regras_auto_aprovacao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[RegraAutoAprovacaoSchema]:
    """Regras de auto-aprovação por template — opcionais, desligadas por padrão (E4-H4)."""
    return aprovacao_service.listar_regras(db, tenant_id)


@router.put("/regras/{template_id}", response_model=RegraAutoAprovacaoSchema)
def definir_regra_auto_aprovacao(
    template_id: str,
    dados: DefinirRegraAutoAprovacaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegraAutoAprovacaoSchema:
    return aprovacao_service.definir_regra(db, tenant_id, ator_id, template_id, dados.habilitada)
