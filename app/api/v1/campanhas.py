from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.campanha import (
    AdicionarDestinatariosAvulsosRequestSchema,
    AdicionarDestinatariosDeDecisoresRequestSchema,
    CampanhaCreateSchema,
    CampanhaDestinatarioSchema,
    CampanhaDetalheSchema,
    CampanhaSchema,
    CampanhaUpdateSchema,
)
from app.services import campanha_service

router = APIRouter(prefix="/campanhas", tags=["campanhas"])


@router.post("", response_model=CampanhaSchema, status_code=201)
def criar_campanha(
    dados: CampanhaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CampanhaSchema:
    return campanha_service.criar(
        db, tenant_id, ator_id, dados.nome, dados.tipo, dados.canais, dados.assunto, dados.conteudo_email, dados.template_whatsapp_id
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
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CampanhaSchema:
    return campanha_service.marcar_pronta(db, tenant_id, ator_id, campanha_id)
