from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_llm_provider, get_tenant_id, get_usuario_atual
from app.contexts.map import contract as map_contract
from app.llm.base import LLMProvider
from app.models.usuario import Usuario
from app.schemas.auth import UsuarioSchema
from app.schemas.conta import ContaSchema
from app.schemas.crm import DashboardEconomiaSchema, DashboardFunilSchema, VendedorComContasSchema
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
    tenant_id_selecionado: str | None = None,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> DashboardSaudeContasSchema:
    return DashboardSaudeContasSchema(
        **saude_conta_service.dashboard_saude_contas(db, usuario, vendedor_usuario_id, tenant_id_selecionado)
    )


@router.get("/ranking", response_model=list[SaudeContaSchema])
def ranking(
    vendedor_usuario_id: int | None = None,
    tenant_id_selecionado: str | None = None,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[SaudeContaSchema]:
    return saude_conta_service.ranking_saude_contas(db, usuario, vendedor_usuario_id, tenant_id_selecionado)


@router.get("/contas/{conta_id}/score-risco", response_model=ScoreRiscoContaSchema)
def score_risco(
    conta_id: int,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ScoreRiscoContaSchema:
    return ScoreRiscoContaSchema(**saude_conta_service.calcular_score_risco(db, usuario, conta_id))


@router.get("/contas/{conta_id}/interacoes", response_model=list[InteracaoContaSchema])
def listar_interacoes(
    conta_id: int,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[InteracaoContaSchema]:
    return saude_conta_service.listar_interacoes_da_conta(db, usuario, conta_id)


@router.post("/interacoes", response_model=InteracaoContaSchema, status_code=201)
def registrar_interacao(
    dados: RegistrarInteracaoContaRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> InteracaoContaSchema:
    return saude_conta_service.registrar_interacao(
        db, usuario, ator_id, dados.conta_id, dados.tipo, dados.descricao
    )


@router.get("/contas/{conta_id}/script-resgate", response_model=ScriptResgateContaSchema)
def script_resgate(
    conta_id: int,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ScriptResgateContaSchema:
    return ScriptResgateContaSchema(**saude_conta_service.gerar_script_resgate(db, usuario, conta_id, llm))


@router.get(
    "/contas/{conta_id}/vendedores-disponiveis",
    response_model=list[UsuarioSchema],
    dependencies=[Depends(exigir_papel("admin", "super_admin"))],
)
def vendedores_disponiveis(
    conta_id: int,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[UsuarioSchema]:
    """Vendedores atribuíveis a esta conta: qualquer usuário ativo da
    subárvore de tenants visível a quem chama, não só do tenant exato da
    conta (raio-X 2026-09-11: admin de distribuidor/revendedor cujos
    sub-tenants são estrutura interna do próprio time — matriz/filial —,
    não clientes pagantes separados; `GET /usuarios`, escopado só ao
    tenant do chamador, nunca achava vendedores de outros tenants da
    mesma subárvore)."""
    return saude_conta_service.listar_vendedores_disponiveis(db, usuario, conta_id)


@router.put(
    "/contas/{conta_id}/vendedor",
    response_model=ContaSchema,
    dependencies=[Depends(exigir_papel("admin", "super_admin"))],
)
def atribuir_vendedor(
    conta_id: int,
    dados: AtribuirVendedorRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    return saude_conta_service.atribuir_vendedor(db, usuario, ator_id, conta_id, dados.vendedor_usuario_id)


# Painel de desempenho do MAP (Fase 1, acoplamento C1): antes a tela do
# MAP chamava `/crm/dashboard/*` e `/crm/vendedores-com-contas`, e um
# tenant só-MAP recebia 403. Mesmos payloads, agora servidos pelo MAP
# através do contrato dele (o funil vem do CRM interno via `MapDataSource`).
@router.get("/desempenho/funil", response_model=DashboardFunilSchema)
def desempenho_funil(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFunilSchema:
    return DashboardFunilSchema(**map_contract.funil(db, tenant_id, vendedor_usuario_id))


@router.get("/desempenho/economia", response_model=DashboardEconomiaSchema)
def desempenho_economia(
    periodo: str,
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardEconomiaSchema:
    return DashboardEconomiaSchema(**map_contract.economia(db, tenant_id, periodo, vendedor_usuario_id))


@router.get("/vendedores-com-contas", response_model=list[VendedorComContasSchema])
def vendedores_com_contas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[VendedorComContasSchema]:
    return [VendedorComContasSchema(**item) for item in map_contract.vendedores_com_contas(db, tenant_id)]
