from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_llm_provider, get_tenant_id
from app.llm.base import LLMProvider
from app.schemas.faq import FaqItemCreateSchema, FaqItemSchema, FaqPerguntarRequestSchema, FaqPerguntarResponseSchema
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


@router.post("/perguntar", response_model=FaqPerguntarResponseSchema)
def perguntar_faq(
    dados: FaqPerguntarRequestSchema,
    llm: LLMProvider = Depends(get_llm_provider),
) -> FaqPerguntarResponseSchema:
    """FAQ interativa com IA (raio-X 2026-09-01) — distinta da FaqItem
    curada por tenant acima; qualquer usuário autenticado pode perguntar
    livremente sobre como usar a plataforma, sem limite de uso (respostas
    curtas, custo bem menor que enriquecimento)."""
    return FaqPerguntarResponseSchema(resposta=faq_service.responder(dados.pergunta, llm))
