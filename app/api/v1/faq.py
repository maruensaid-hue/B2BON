from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.schemas.faq import FaqItemCreateSchema, FaqItemSchema
from app.services import faq_service

router = APIRouter(prefix="/faq", tags=["faq"])


@router.post("", response_model=FaqItemSchema, status_code=201)
def criar_faq(
    dados: FaqItemCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> FaqItemSchema:
    """Base de FAQ do assinante, alimentada no onboarding (E5-H4)."""
    return faq_service.criar(db, tenant_id, dados.pergunta, dados.resposta)


@router.get("", response_model=list[FaqItemSchema])
def listar_faq(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[FaqItemSchema]:
    return faq_service.listar(db, tenant_id)
