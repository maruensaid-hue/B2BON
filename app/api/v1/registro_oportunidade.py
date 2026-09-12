from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_plan_limits_provider, get_usuario_atual
from app.models.usuario import Usuario
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.registro_oportunidade import (
    AtualizarStatusRegistroRequestSchema,
    DecidirSolicitacaoDescontoRequestSchema,
    RegistrarOportunidadeRequestSchema,
    RegistroOportunidadeSchema,
    SolicitacaoDescontoSchema,
    SolicitarDescontoRequestSchema,
)
from app.services import registro_oportunidade_service

router = APIRouter(prefix="/registro-oportunidade", tags=["registro-oportunidade"])


@router.post("", response_model=RegistroOportunidadeSchema, status_code=201)
def registrar_oportunidade(
    dados: RegistrarOportunidadeRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> RegistroOportunidadeSchema:
    return registro_oportunidade_service.registrar_oportunidade(
        db, usuario, ator_id, plan_limits, dados.cnpj, dados.nome_empresa, dados.conta_id
    )


@router.get("", response_model=list[RegistroOportunidadeSchema])
def listar_registros(
    tenant_id_selecionado: str | None = None,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[RegistroOportunidadeSchema]:
    return registro_oportunidade_service.listar_registros(db, usuario, tenant_id_selecionado)


@router.put("/{registro_id}/status", response_model=RegistroOportunidadeSchema)
def atualizar_status(
    registro_id: int,
    dados: AtualizarStatusRegistroRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> RegistroOportunidadeSchema:
    return registro_oportunidade_service.atualizar_status(db, usuario, ator_id, registro_id, dados.status)


@router.post("/{registro_id}/solicitar-desconto", response_model=SolicitacaoDescontoSchema, status_code=201)
def solicitar_desconto(
    registro_id: int,
    dados: SolicitarDescontoRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SolicitacaoDescontoSchema:
    return registro_oportunidade_service.solicitar_desconto(
        db, usuario, ator_id, registro_id, dados.percentual_solicitado, dados.justificativa
    )


@router.get("/solicitacoes-desconto", response_model=list[SolicitacaoDescontoSchema])
def listar_solicitacoes_desconto(
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[SolicitacaoDescontoSchema]:
    return registro_oportunidade_service.listar_solicitacoes_desconto(db, usuario)


@router.put(
    "/solicitacoes-desconto/{solicitacao_id}",
    response_model=SolicitacaoDescontoSchema,
    dependencies=[Depends(exigir_papel("admin", "super_admin"))],
)
def decidir_solicitacao_desconto(
    solicitacao_id: int,
    dados: DecidirSolicitacaoDescontoRequestSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SolicitacaoDescontoSchema:
    return registro_oportunidade_service.decidir_solicitacao_desconto(
        db, usuario, ator_id, solicitacao_id, dados.aprovar, dados.motivo
    )
