from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_plan_limits_provider, get_tenant_id, limitar_ia_por_tenant
from app.llm.base import LLMProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.cadencia import (
    AdicionarToqueRequestSchema,
    AtivarCadenciaResponseSchema,
    AtualizarToqueRequestSchema,
    CadenciaCreateSchema,
    CadenciaSchema,
    CancelarCadenciaResponseSchema,
    DefinirCancelamentoAoResponderRequestSchema,
    DefinirTemplateWhatsAppRequestSchema,
    GerarCadenciaRequestSchema,
    GerarCadenciaResponseSchema,
    RelatorioAbTesteSchema,
    RenomearCadenciaRequestSchema,
    ToqueCadenciaSchema,
)
from app.services import ab_teste_service, cadencia_service

router = APIRouter(prefix="/cadencias", tags=["cadencias"])


@router.post("", response_model=CadenciaSchema, status_code=201)
def criar_cadencia(
    dados: CadenciaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> CadenciaSchema:
    return cadencia_service.criar(db, tenant_id, ator_id, dados, plan_limits)


@router.get("", response_model=list[CadenciaSchema])
def listar_cadencias(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[CadenciaSchema]:
    return cadencia_service.listar(db, tenant_id)


@router.delete("/{cadencia_id}", status_code=204)
def excluir_cadencia(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    cadencia_service.excluir(db, tenant_id, ator_id, cadencia_id)


@router.get("/{cadencia_id}/toques", response_model=list[ToqueCadenciaSchema])
def listar_toques(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ToqueCadenciaSchema]:
    cadencia_service.obter(db, tenant_id, cadencia_id)
    return cadencia_service.toques_da_cadencia(db, cadencia_id)


@router.post("/{cadencia_id}/toques", response_model=ToqueCadenciaSchema, status_code=201)
def adicionar_toque(
    cadencia_id: int,
    dados: AdicionarToqueRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ToqueCadenciaSchema:
    """Adiciona um toque a uma cadência já existente — só afeta contas
    geradas a partir de agora (raio-X 2026-09-15)."""
    return cadencia_service.adicionar_toque(
        db, tenant_id, ator_id, cadencia_id, dados.canal, dados.intervalo_dias_apos_anterior,
        dados.template_whatsapp_id, dados.ab_teste_habilitado,
    )


@router.put("/{cadencia_id}/toques/{toque_id}", response_model=ToqueCadenciaSchema)
def atualizar_toque(
    cadencia_id: int,
    toque_id: int,
    dados: AtualizarToqueRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ToqueCadenciaSchema:
    """Troca canal/intervalo/teste A/B de um toque já existente — raio-X
    2026-09-15, distinto de `.../template-whatsapp`."""
    return cadencia_service.atualizar_toque(
        db, tenant_id, ator_id, cadencia_id, toque_id,
        dados.canal, dados.intervalo_dias_apos_anterior, dados.ab_teste_habilitado,
    )


@router.delete("/{cadencia_id}/toques/{toque_id}", status_code=204)
def remover_toque(
    cadencia_id: int,
    toque_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    cadencia_service.remover_toque(db, tenant_id, ator_id, cadencia_id, toque_id)


@router.put("/{cadencia_id}/toques/{toque_id}/template-whatsapp", response_model=ToqueCadenciaSchema)
def definir_template_whatsapp(
    cadencia_id: int,
    toque_id: int,
    dados: DefinirTemplateWhatsAppRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ToqueCadenciaSchema:
    """Define/troca o template de um toque de WhatsApp já existente — pra
    quem criou a cadência antes do template ser aprovado pela Meta
    (raio-X 2026-09-15)."""
    return cadencia_service.definir_template_whatsapp(
        db, tenant_id, ator_id, cadencia_id, toque_id, dados.template_whatsapp_id
    )


@router.get("/{cadencia_id}", response_model=CadenciaSchema)
def obter_cadencia(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CadenciaSchema:
    return cadencia_service.obter(db, tenant_id, cadencia_id)


@router.put("/{cadencia_id}", response_model=CadenciaSchema)
def renomear_cadencia(
    cadencia_id: int,
    dados: RenomearCadenciaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CadenciaSchema:
    return cadencia_service.renomear(db, tenant_id, ator_id, cadencia_id, dados.nome)


@router.put("/{cadencia_id}/cancelamento-ao-responder", response_model=CadenciaSchema)
def definir_cancelamento_ao_responder(
    cadencia_id: int,
    dados: DefinirCancelamentoAoResponderRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CadenciaSchema:
    """Liga/desliga o cancelamento automático ao responder — desligado
    por padrão desde a criação (raio-X 2026-09-15)."""
    return cadencia_service.definir_cancelamento_ao_responder(
        db, tenant_id, ator_id, cadencia_id, dados.cancelar_ao_responder
    )


@router.post("/{cadencia_id}/cancelar", response_model=CancelarCadenciaResponseSchema)
def cancelar_cadencia(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CancelarCadenciaResponseSchema:
    """Para qualquer envio futuro a partir de agora, sem apagar nada do
    histórico já enviado (raio-X 2026-09-15 — "excluir mesmo já
    disparada" virou "cancelar", ver `cadencia_service.cancelar`)."""
    return CancelarCadenciaResponseSchema(**cadencia_service.cancelar(db, tenant_id, ator_id, cadencia_id))


@router.post("/{cadencia_id}/gerar", response_model=GerarCadenciaResponseSchema, dependencies=[Depends(limitar_ia_por_tenant())])
def gerar_cadencia_para_lote(
    cadencia_id: int,
    dados: GerarCadenciaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> GerarCadenciaResponseSchema:
    resultado = cadencia_service.gerar_para_lote(db, tenant_id, ator_id, cadencia_id, dados.conta_ids, llm, plan_limits)
    return GerarCadenciaResponseSchema(**resultado)


@router.post("/{cadencia_id}/ativar", response_model=AtivarCadenciaResponseSchema)
def ativar_cadencia(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> AtivarCadenciaResponseSchema:
    resultado = cadencia_service.ativar(db, tenant_id, ator_id, cadencia_id, plan_limits)
    return AtivarCadenciaResponseSchema(**resultado)


@router.get("/{cadencia_id}/teste-ab", response_model=RelatorioAbTesteSchema)
def relatorio_teste_ab(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> RelatorioAbTesteSchema:
    """Relatório de vencedora do teste A/B por taxa de resposta (E3-H5)."""
    return RelatorioAbTesteSchema(**ab_teste_service.relatorio(db, tenant_id, cadencia_id))
