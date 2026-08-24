from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.conta import ContaSchema, CriarLeadRequestSchema
from app.schemas.decisor import DecisorSchema
from app.schemas.lista_prospeccao import ExcluirContasResponseSchema
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


@router.delete("/contas", response_model=ExcluirContasResponseSchema, dependencies=[Depends(exigir_papel("super_admin"))])
def excluir_todos_os_leads(
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ExcluirContasResponseSchema:
    """Apaga em lote todos os leads avulsos — só super_admin (pedido do
    usuário: "somente a mim como Super Admin"). Mesmo crivo de segurança
    da exclusão de conta: recusa apagar quem já tem negócio/mensagem/
    reunião etc., não aborta o lote inteiro por causa de uma bloqueada."""
    resultado = conta_service.excluir_lote_leads(db, tenant_id, ator_id, usuario)
    return ExcluirContasResponseSchema(**resultado)


@router.get("/decisores", response_model=list[DecisorSchema])
def listar_decisores_leads(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[DecisorSchema]:
    return conta_service.listar_decisores_leads(db, tenant_id, usuario, vendedor_usuario_id)
