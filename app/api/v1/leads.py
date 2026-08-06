from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.conta import ContaSchema, CriarLeadRequestSchema
from app.schemas.decisor import DecisorSchema
from app.services import conta_service

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("/contas", response_model=ContaSchema, status_code=201)
def criar_lead(
    dados: CriarLeadRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    """Cliente avulso cadastrado direto no CRM — sem ICP, para quem foi
    conquistado por indicação/evento/contato pessoal, fora do recorte
    estático de segmento/porte/dor de um ICP."""
    return conta_service.criar_lead(
        db, tenant_id, ator_id, dados.nome, dados.cnpj, dados.dominio, dados.segmento, dados.porte, dados.regiao
    )


@router.get("/contas", response_model=list[ContaSchema])
def listar_leads(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ContaSchema]:
    return conta_service.listar_leads(db, tenant_id, usuario, vendedor_usuario_id)


@router.get("/decisores", response_model=list[DecisorSchema])
def listar_decisores_leads(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[DecisorSchema]:
    return conta_service.listar_decisores_leads(db, tenant_id, usuario, vendedor_usuario_id)
