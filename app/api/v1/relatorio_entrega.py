from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.relatorio_entrega import ListaEnviosEmailSchema, RelatorioEntregaSchema
from app.services import relatorio_entrega_service

router = APIRouter(prefix="/relatorio-entrega", tags=["relatorio-entrega"])


@router.get("", response_model=RelatorioEntregaSchema)
def obter_relatorio_entrega(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> RelatorioEntregaSchema:
    """Raio-X 2026-09-16 — combina saúde do canal de e-mail (`reputacao_
    service`, já existente mas nunca exposto no frontend), taxa de
    abertura/resposta (`panel_service`, idem) e a lista de contatos que
    causaram bounce, pra viabilizar "corrigir o e-mail ou excluir o
    contato" na prática."""
    return RelatorioEntregaSchema(**relatorio_entrega_service.obter(db, tenant_id))


@router.get("/envios", response_model=ListaEnviosEmailSchema)
def listar_envios_email(
    status: str = "todos",
    limite: int = 50,
    offset: int = 0,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ListaEnviosEmailSchema:
    """Raio-X 2026-09-17 — o KPI "Enviados" agregado só contava
    confirmação "delivered" já recebida via webhook do SendGrid, o que
    sub-representava o real (ex.: 2 cadências ativadas com dezenas de
    destinatários mostravam "2"). Esta lista mostra cada mensagem/
    destinatário de e-mail individualmente, com status e motivo real."""
    return ListaEnviosEmailSchema(**relatorio_entrega_service.listar_envios_email(db, tenant_id, status, limite, offset))
