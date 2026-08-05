from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_llm_provider, get_tenant_id, get_usuario_atual
from app.llm.base import LLMProvider
from app.models.usuario import Usuario
from app.schemas.conta import ContaSchema
from app.schemas.saude_conta import (
    AtribuirVendedorRequestSchema,
    DashboardSaudeContasSchema,
    InteracaoContaSchema,
    RegistrarInteracaoContaRequestSchema,
    SaudeContaSchema,
    ScoreRiscoContaSchema,
    ScriptResgateContaSchema,
)
from app.services import saude_conta_service

router = APIRouter(prefix="/saude-contas", tags=["saude-contas"])


@router.get("/dashboard", response_model=DashboardSaudeContasSchema)
def dashboard(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> DashboardSaudeContasSchema:
    return DashboardSaudeContasSchema(
        **saude_conta_service.dashboard_saude_contas(db, tenant_id, usuario, vendedor_usuario_id)
    )


@router.get("/ranking", response_model=list[SaudeContaSchema])
def ranking(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[SaudeContaSchema]:
    return saude_conta_service.ranking_saude_contas(db, tenant_id, usuario, vendedor_usuario_id)


@router.get("/contas/{conta_id}/score-risco", response_model=ScoreRiscoContaSchema)
def score_risco(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ScoreRiscoContaSchema:
    return ScoreRiscoContaSchema(**saude_conta_service.calcular_score_risco(db, tenant_id, conta_id))


@router.get("/contas/{conta_id}/interacoes", response_model=list[InteracaoContaSchema])
def listar_interacoes(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[InteracaoContaSchema]:
    return saude_conta_service.listar_interacoes(db, tenant_id, conta_id)


@router.post("/interacoes", response_model=InteracaoContaSchema, status_code=201)
def registrar_interacao(
    dados: RegistrarInteracaoContaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> InteracaoContaSchema:
    return saude_conta_service.registrar_interacao(
        db, tenant_id, ator_id, dados.conta_id, dados.tipo, dados.descricao
    )


@router.get("/contas/{conta_id}/script-resgate", response_model=ScriptResgateContaSchema)
def script_resgate(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ScriptResgateContaSchema:
    return ScriptResgateContaSchema(**saude_conta_service.gerar_script_resgate(db, tenant_id, conta_id, llm))


@router.put(
    "/contas/{conta_id}/vendedor",
    response_model=ContaSchema,
    dependencies=[Depends(exigir_papel("admin", "super_admin"))],
)
def atribuir_vendedor(
    conta_id: int,
    dados: AtribuirVendedorRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    return saude_conta_service.atribuir_vendedor(db, tenant_id, ator_id, conta_id, dados.vendedor_usuario_id)
