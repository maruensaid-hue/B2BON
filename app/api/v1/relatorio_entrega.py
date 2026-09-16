from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.relatorio_entrega import RelatorioEntregaSchema
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
