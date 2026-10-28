import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from sqlalchemy.orm import Session

from app.api.deps import (
    get_ator_id,
    get_db,
    get_plan_limits_provider,
    get_sessao_factory,
    get_tenant_id,
    resolver_email_provider,
    resolver_whatsapp_provider,
)
from app.models.tenant import Tenant
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.campanha import (
    AdicionarDestinatariosAvulsosRequestSchema,
    AdicionarDestinatariosDeDecisoresRequestSchema,
    CampanhaCreateSchema,
    CampanhaDestinatarioSchema,
    CampanhaDetalheSchema,
    CampanhaPreviaSchema,
    CampanhaSchema,
    CampanhaUpdateSchema,
    EditarDestinatarioRequestSchema,
    MarcarProntaRequestSchema,
    NaoQuerReceberRequestSchema,
)
from app.services import campanha_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campanhas", tags=["campanhas"])


def _disparar_em_segundo_plano(sessao_factory, tenant_id: str, campanha_id: int) -> None:
    """Começa o envio logo depois da resposta de "Marcar como pronta", sem esperar o agendador externo (que o GitHub atrasa ou descarta). Sessão
    própria. Se falhar ou o processo cair, a campanha segue `pronta`/`enviando` e o agendador continua de onde parou; a reserva da campanha impede que
    os dois enviem ao mesmo tempo. Ambientes de demonstração e tenants inativos ficam de fora, como no agendador."""
    sessao = sessao_factory()
    try:
        tenant = sessao.get(Tenant, tenant_id)
        if tenant is None or not tenant.ativo or tenant.demo_expira_em is not None:
            return
        whatsapp = resolver_whatsapp_provider(tenant_id, sessao)
        email = resolver_email_provider(tenant_id, sessao)
        campanha_service.processar_pendentes(sessao, tenant_id, email, whatsapp, campanha_id=campanha_id)
    except Exception:  # noqa: BLE001 — tarefa sem chamador para propagar
        logger.exception("CAMPANHA_DISPARO_IMEDIATO_FALHOU campanha=%s", campanha_id)
        sessao.rollback()
    finally:
        sessao.close()


@router.post("", response_model=CampanhaSchema, status_code=201)
def criar_campanha(
    dados: CampanhaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> CampanhaSchema:
    return campanha_service.criar(
        db,
        tenant_id,
        ator_id,
        dados.nome,
        dados.tipo,
        dados.canais,
        dados.assunto,
        dados.conteudo_email,
        dados.template_whatsapp_id,
        plan_limits,
    )


@router.get("", response_model=list[CampanhaSchema])
def listar_campanhas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[CampanhaSchema]:
    return campanha_service.listar(db, tenant_id)


@router.get("/{campanha_id}", response_model=CampanhaDetalheSchema)
def obter_campanha(
    campanha_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CampanhaDetalheSchema:
    campanha = campanha_service.obter(db, tenant_id, campanha_id)
    destinatarios = campanha_service.listar_destinatarios(db, tenant_id, campanha_id)
    metricas = campanha_service.metricas(db, tenant_id, campanha_id)
    return CampanhaDetalheSchema(
        **CampanhaSchema.model_validate(campanha).model_dump(),
        destinatarios=[CampanhaDestinatarioSchema.model_validate(d) for d in destinatarios],
        metricas=metricas,
    )


@router.get("/{campanha_id}/previa", response_model=CampanhaPreviaSchema)
def previa_campanha(
    campanha_id: int,
    destinatario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CampanhaPreviaSchema:
    """E-mail como chega para um destinatário (o indicado ou o primeiro da lista), com `[Nome]` e `[Empresa]` já trocados e sem o rodapé de descadastro."""
    return CampanhaPreviaSchema(**campanha_service.previa(db, tenant_id, campanha_id, destinatario_id))


@router.put("/{campanha_id}", response_model=CampanhaSchema)
def atualizar_campanha(
    campanha_id: int,
    dados: CampanhaUpdateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CampanhaSchema:
    return campanha_service.atualizar(
        db,
        tenant_id,
        ator_id,
        campanha_id,
        dados.nome,
        dados.tipo,
        dados.canais,
        dados.assunto,
        dados.conteudo_email,
        dados.template_whatsapp_id,
    )


@router.post("/{campanha_id}/voltar-para-rascunho", response_model=CampanhaSchema)
def voltar_para_rascunho(
    campanha_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CampanhaSchema:
    """Devolve a campanha ao rascunho para editar o texto: quem já recebeu continua enviado, os que falharam voltam à fila e um envio em andamento para."""
    return campanha_service.voltar_para_rascunho(db, tenant_id, ator_id, campanha_id)


@router.delete("/{campanha_id}", status_code=204)
def excluir_campanha(
    campanha_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    campanha_service.excluir(db, tenant_id, ator_id, campanha_id)


@router.post("/{campanha_id}/destinatarios/decisores", response_model=list[CampanhaDestinatarioSchema], status_code=201)
def adicionar_destinatarios_de_decisores(
    campanha_id: int,
    dados: AdicionarDestinatariosDeDecisoresRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> list[CampanhaDestinatarioSchema]:
    return campanha_service.adicionar_de_decisores(db, tenant_id, ator_id, campanha_id, dados.decisor_ids)


@router.post("/{campanha_id}/destinatarios/avulsos", response_model=list[CampanhaDestinatarioSchema], status_code=201)
def adicionar_destinatarios_avulsos(
    campanha_id: int,
    dados: AdicionarDestinatariosAvulsosRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> list[CampanhaDestinatarioSchema]:
    return campanha_service.adicionar_avulsos(db, tenant_id, ator_id, campanha_id, dados.destinatarios)


@router.put("/{campanha_id}/destinatarios/{destinatario_id}", response_model=CampanhaDestinatarioSchema)
def editar_destinatario(
    campanha_id: int,
    destinatario_id: int,
    dados: EditarDestinatarioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CampanhaDestinatarioSchema:
    """Corrige nome, e-mail, telefone ou empresa de um destinatário, com a campanha parada. As regras estão em `campanha_service.editar_destinatario`."""
    return campanha_service.editar_destinatario(
        db, tenant_id, ator_id, campanha_id, destinatario_id,
        dados.nome, dados.email, dados.telefone, dados.empresa, dados.reenviar, dados.atualizar_contato_crm,
    )


@router.post("/{campanha_id}/destinatarios/{destinatario_id}/nao-quer-receber", response_model=CampanhaDestinatarioSchema)
def nao_quer_receber(
    campanha_id: int,
    destinatario_id: int,
    dados: NaoQuerReceberRequestSchema | None = None,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CampanhaDestinatarioSchema:
    """Cancela o destinatário e põe o e-mail e o telefone dele na lista de bloqueio da empresa, que vale para todas as campanhas."""
    return campanha_service.nao_quer_receber(
        db, tenant_id, ator_id, campanha_id, destinatario_id, dados.motivo if dados is not None else None
    )


@router.delete("/{campanha_id}/destinatarios/{destinatario_id}", status_code=204)
def remover_destinatario(
    campanha_id: int,
    destinatario_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    campanha_service.remover_destinatario(db, tenant_id, ator_id, campanha_id, destinatario_id)


@router.post("/{campanha_id}/marcar-pronta", response_model=CampanhaSchema)
def marcar_pronta(
    campanha_id: int,
    tarefas: BackgroundTasks,
    dados: MarcarProntaRequestSchema | None = None,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    sessao_factory=Depends(get_sessao_factory),
) -> CampanhaSchema:
    campanha = campanha_service.marcar_pronta(
        db, tenant_id, ator_id, campanha_id, dados.destinatario_ids if dados is not None else None
    )
    if sessao_factory is not None:  # nos testes a fábrica é `None`: o envio é exercitado direto no serviço
        tarefas.add_task(_disparar_em_segundo_plano, sessao_factory, tenant_id, campanha_id)
    return campanha
