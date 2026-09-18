from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_tenant_id
from app.llm.base import LLMProvider
from app.schemas.regra_aprendida import (
    CorrecaoRecenteSchema,
    PadroesObservadosSchema,
    PerformanceIaSchema,
    RegraAprendidaCreateSchema,
    RegraAprendidaSchema,
    SugestaoRegraSchema,
)
from app.services import metricas_service, regra_aprendida_service

router = APIRouter(prefix="/regras-aprendidas", tags=["regras-aprendidas"])


@router.get("/correcoes-recentes", response_model=list[CorrecaoRecenteSchema])
def listar_correcoes_recentes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[CorrecaoRecenteSchema]:
    """Edições/rejeições recentes de mensagens geradas por IA (raio-X
    2026-09-17) — o humano decide, ao ver o padrão, se cria uma
    `RegraAprendida` durável a partir daquele caso."""
    return regra_aprendida_service.listar_correcoes_recentes(db, tenant_id)


@router.get("/performance-ia", response_model=PerformanceIaSchema)
def calcular_performance_ia(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> PerformanceIaSchema:
    """AI Performance metrics (master prompt §77, Fase 6D)."""
    return PerformanceIaSchema(**regra_aprendida_service.calcular_performance_ia(db, tenant_id))


@router.get("/padroes-observados", response_model=PadroesObservadosSchema)
def calcular_padroes_observados(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> PadroesObservadosSchema:
    """Company Learning (master prompt §12, §15, Fase 0.5-B)."""
    return PadroesObservadosSchema(**metricas_service.calcular_padroes_observados(db, tenant_id))


@router.post("/correcoes-recentes/{log_id}/sugerir-regra", response_model=SugestaoRegraSchema)
def sugerir_regra_com_ia(
    log_id: int,
    tenant_id: str = Depends(get_tenant_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> SugestaoRegraSchema:
    """Peça 3 do loop de aprendizado (raio-X 2026-09-17) — sugere só o
    texto, nunca cria a regra: o humano ainda decide no formulário."""
    return SugestaoRegraSchema(regra_sugerida=regra_aprendida_service.sugerir_regra_com_ia(db, tenant_id, log_id, llm))


@router.post("", response_model=RegraAprendidaSchema, status_code=201)
def criar_regra_aprendida(
    dados: RegraAprendidaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegraAprendidaSchema:
    return regra_aprendida_service.criar(db, tenant_id, ator_id, dados)


@router.get("", response_model=list[RegraAprendidaSchema])
def listar_regras_aprendidas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[RegraAprendidaSchema]:
    return regra_aprendida_service.listar(db, tenant_id)


@router.put("/{regra_id}", response_model=RegraAprendidaSchema)
def atualizar_regra_aprendida(
    regra_id: int,
    dados: RegraAprendidaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegraAprendidaSchema:
    return regra_aprendida_service.atualizar(db, tenant_id, ator_id, regra_id, dados)


@router.post("/{regra_id}/ativar", response_model=RegraAprendidaSchema)
def ativar_regra_aprendida(
    regra_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegraAprendidaSchema:
    return regra_aprendida_service.ativar(db, tenant_id, ator_id, regra_id)


@router.post("/{regra_id}/desativar", response_model=RegraAprendidaSchema)
def desativar_regra_aprendida(
    regra_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegraAprendidaSchema:
    return regra_aprendida_service.desativar(db, tenant_id, ator_id, regra_id)


@router.delete("/{regra_id}", status_code=204)
def excluir_regra_aprendida(
    regra_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    regra_aprendida_service.excluir(db, tenant_id, ator_id, regra_id)
