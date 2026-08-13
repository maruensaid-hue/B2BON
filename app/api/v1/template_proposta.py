from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
from app.schemas.template_proposta import (
    AtualizarItemTemplatePropostaRequestSchema,
    AtualizarTemplatePropostaRequestSchema,
    CriarItemTemplatePropostaRequestSchema,
    ItemTemplatePropostaSchema,
    TemplatePropostaSchema,
)
from app.services import template_proposta_service

router = APIRouter(prefix="/template-proposta", tags=["template-proposta"])


@router.get("", response_model=TemplatePropostaSchema)
def obter_template(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> TemplatePropostaSchema:
    return template_proposta_service.obter_ou_criar(db, tenant_id)


@router.put("", response_model=TemplatePropostaSchema)
def atualizar_template(
    dados: AtualizarTemplatePropostaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> TemplatePropostaSchema:
    return template_proposta_service.atualizar(
        db,
        tenant_id,
        ator_id,
        dados.texto_introdutorio,
        dados.termo_aceite,
        dados.mostrar_tabela_produtos,
        dados.mostrar_tabela_servicos,
    )


@router.post("/logo", response_model=TemplatePropostaSchema)
async def enviar_logo(
    arquivo: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> TemplatePropostaSchema:
    conteudo = await arquivo.read()
    return template_proposta_service.salvar_logo(db, tenant_id, ator_id, conteudo, arquivo.content_type or "")


@router.get("/logo")
def baixar_logo(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    template = template_proposta_service.obter_ou_criar(db, tenant_id)
    if not template.logo_conteudo:
        return Response(status_code=404)
    return Response(content=template.logo_conteudo, media_type=template.logo_tipo_mime or "image/png")


@router.get("/itens", response_model=list[ItemTemplatePropostaSchema])
def listar_itens(
    tipo: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ItemTemplatePropostaSchema]:
    return template_proposta_service.listar_itens(db, tenant_id, tipo)


@router.post("/itens", response_model=ItemTemplatePropostaSchema, status_code=201)
def adicionar_item(
    dados: CriarItemTemplatePropostaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ItemTemplatePropostaSchema:
    return template_proposta_service.adicionar_item(db, tenant_id, ator_id, dados.tipo, dados.descricao, dados.valor)


@router.put("/itens/{item_id}", response_model=ItemTemplatePropostaSchema)
def atualizar_item(
    item_id: int,
    dados: AtualizarItemTemplatePropostaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ItemTemplatePropostaSchema:
    return template_proposta_service.atualizar_item(db, tenant_id, item_id, dados.descricao, dados.valor)


@router.delete("/itens/{item_id}", status_code=204)
def remover_item(
    item_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    template_proposta_service.remover_item(db, tenant_id, item_id)
