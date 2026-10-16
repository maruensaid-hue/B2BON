from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    exigir_papel, exigir_escopo_aprovacao_usuario, exigir_escopo_mensagem_usuario,
    get_ator_id, get_db, get_plan_limits_provider, get_tenant_id, get_usuario_atual,
)
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.aprovacao import (
    AprovacaoFilaItemSchema,
    AprovacaoSchema,
    AprovarLoteRequestSchema,
    DefinirRegraAutoAprovacaoRequestSchema,
    EditarMensagemRequestSchema,
    ExcluirLoteResponseSchema,
    RegraAutoAprovacaoSchema,
    RejeitarRequestSchema,
)
from app.schemas.mensagem import MensagemSchema
from app.models.usuario import Usuario
from app.models.aprovacao import Aprovacao
from app.models.mensagem import Mensagem
from app.models.decisor import Decisor
from app.models.conta import Conta
from app.models.icp import ICP
from app.services.errors import NaoEncontrado
from app.services import aprovacao_service

router = APIRouter(prefix="/aprovacoes", tags=["aprovacoes"])


def _validar_ids_aprovacao_no_escopo(
    db: Session, tenant_id: str, ids: list[int], usuario: Usuario
) -> None:
    if usuario.papel != "user" or not ids:
        return
    permitidos = {
        aprovacao_id for (aprovacao_id,) in (
            db.query(Aprovacao.id)
            .join(Mensagem, Mensagem.id == Aprovacao.mensagem_id)
            .join(Decisor, Decisor.id == Mensagem.decisor_id)
            .join(Conta, Conta.id == Decisor.conta_id)
            .outerjoin(ICP, ICP.id == Conta.icp_id)
            .filter(
                Aprovacao.tenant_id == tenant_id,
                Aprovacao.id.in_(ids),
                Mensagem.tenant_id == tenant_id,
                Conta.tenant_id == tenant_id,
                ((Conta.vendedor_usuario_id == usuario.id) | (Conta.criado_por_usuario_id == usuario.id)
                 | (ICP.criador_usuario_id == usuario.id)),
                ((Conta.vendedor_usuario_id.is_(None)) | (Conta.vendedor_usuario_id == usuario.id)),
                ((Decisor.criado_por_usuario_id == usuario.id) | (ICP.criador_usuario_id == usuario.id)),
            )
            .all()
        )
    }
    if permitidos != set(ids):
        raise NaoEncontrado("Uma ou mais aprovações não foram encontradas no seu escopo.")


@router.get("", response_model=list[AprovacaoFilaItemSchema])
def listar_fila(
    canal: str | None = None,
    conta_id: int | None = None,
    cadencia_id: int | None = None,
    status: str | None = None,
    decisor_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[AprovacaoFilaItemSchema]:
    itens = aprovacao_service.listar_fila(
        db, tenant_id, canal, conta_id, cadencia_id, status, decisor_id, usuario.id, usuario.papel == "user"
    )
    return [AprovacaoFilaItemSchema(**item) for item in itens]


@router.post("/mensagens/{mensagem_id}/cancelar", response_model=MensagemSchema, dependencies=[Depends(exigir_escopo_mensagem_usuario)])
def cancelar_mensagem(
    mensagem_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MensagemSchema:
    """Cancela uma mensagem agendada/pendente individualmente, sem apagar
    o histórico — raio-X 2026-09-15 (ver `aprovacao_service.cancelar_mensagem`)."""
    return aprovacao_service.cancelar_mensagem(db, tenant_id, ator_id, mensagem_id)


@router.post("/aprovar-lote", response_model=list[AprovacaoSchema])
def aprovar_lote(
    dados: AprovarLoteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[AprovacaoSchema]:
    _validar_ids_aprovacao_no_escopo(db, tenant_id, dados.ids, usuario)
    return aprovacao_service.aprovar_lote(db, tenant_id, ator_id, dados.ids)


@router.post("/{aprovacao_id}/aprovar", response_model=AprovacaoSchema, dependencies=[Depends(exigir_escopo_aprovacao_usuario)])
def aprovar(
    aprovacao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> AprovacaoSchema:
    return aprovacao_service.aprovar(db, tenant_id, ator_id, aprovacao_id)


@router.post("/{aprovacao_id}/rejeitar", response_model=AprovacaoSchema, dependencies=[Depends(exigir_escopo_aprovacao_usuario)])
def rejeitar(
    aprovacao_id: int,
    dados: RejeitarRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> AprovacaoSchema:
    return aprovacao_service.rejeitar(db, tenant_id, ator_id, aprovacao_id, dados.motivo)


@router.delete("/{aprovacao_id}", status_code=204, dependencies=[Depends(exigir_escopo_aprovacao_usuario)])
def excluir(
    aprovacao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    aprovacao_service.excluir(db, tenant_id, ator_id, aprovacao_id)


@router.post("/excluir-lote", response_model=ExcluirLoteResponseSchema)
def excluir_lote(
    dados: AprovarLoteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ExcluirLoteResponseSchema:
    _validar_ids_aprovacao_no_escopo(db, tenant_id, dados.ids, usuario)
    return ExcluirLoteResponseSchema(excluidas=aprovacao_service.excluir_lote(db, tenant_id, ator_id, dados.ids))


@router.put("/{aprovacao_id}/mensagem", response_model=MensagemSchema, dependencies=[Depends(exigir_escopo_aprovacao_usuario)])
def editar_mensagem(
    aprovacao_id: int,
    dados: EditarMensagemRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> MensagemSchema:
    return aprovacao_service.editar_mensagem(db, tenant_id, ator_id, aprovacao_id, dados.conteudo)


@router.get("/regras", response_model=list[RegraAutoAprovacaoSchema], dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def listar_regras_auto_aprovacao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[RegraAutoAprovacaoSchema]:
    """Regras de auto-aprovação por template — opcionais, desligadas por padrão (E4-H4)."""
    return aprovacao_service.listar_regras(db, tenant_id)


@router.put("/regras/{template_id}", response_model=RegraAutoAprovacaoSchema, dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def definir_regra_auto_aprovacao(
    template_id: str,
    dados: DefinirRegraAutoAprovacaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> RegraAutoAprovacaoSchema:
    return aprovacao_service.definir_regra(db, tenant_id, ator_id, template_id, dados.habilitada, plan_limits)
