from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id, get_usuario_atual
from app.models.usuario import Usuario
from app.schemas.conta import ContaSchema, CriarLeadRequestSchema
from app.schemas.decisor import DecisorSchema
from app.schemas.lista_prospeccao import (
    ElegibilidadeContaSchema,
    ExcluirContasRequestSchema,
    ExcluirContasResponseSchema,
    PreviaLimpezaLeadsSchema,
)
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


@router.get(
    "/contas/elegibilidade-exclusao",
    response_model=list[ElegibilidadeContaSchema],
    dependencies=[Depends(exigir_papel("super_admin"))],
)
def elegibilidade_exclusao_leads(
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[ElegibilidadeContaSchema]:
    """Pré-visualização antes de excluir em lote: para cada lead, diz se ele
    pode ser apagado ou não (e por quê — negócio, mensagem, indicação
    etc.), sem apagar nada. O frontend usa isso pra montar a lista com
    caixas de seleção (bloqueados já vêm desmarcados)."""
    contas = conta_service.listar_leads(db, tenant_id, usuario)
    return conta_service.mapear_elegibilidade_exclusao(db, contas)


@router.delete("/contas", response_model=ExcluirContasResponseSchema, dependencies=[Depends(exigir_papel("super_admin"))])
def excluir_todos_os_leads(
    dados: ExcluirContasRequestSchema | None = Body(default=None),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ExcluirContasResponseSchema:
    """Apaga em lote os leads avulsos — só super_admin (pedido do usuário:
    "somente a mim como Super Admin"). Mesmo crivo de segurança da exclusão
    de conta: recusa apagar quem já tem negócio/mensagem/reunião etc., não
    aborta o lote inteiro por causa de uma bloqueada. `conta_ids` (opcional)
    restringe aos leads escolhidos no frontend a partir da pré-visualização
    de elegibilidade; sem isso, tenta todos os leads visíveis."""
    conta_ids = dados.conta_ids if dados is not None else None
    resultado = conta_service.excluir_lote_leads(db, tenant_id, ator_id, usuario, conta_ids)
    return ExcluirContasResponseSchema(**resultado)


@router.get(
    "/contas/preview-limpeza-nao-trabalhados",
    response_model=PreviaLimpezaLeadsSchema,
    dependencies=[Depends(exigir_papel("super_admin"))],
)
def preview_limpeza_leads_nao_trabalhados(
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> PreviaLimpezaLeadsSchema:
    """Pré-visualização (sem apagar nada) de uma limpeza pontual, mais
    agressiva que `DELETE /leads/contas`: mantém só quem já tem
    oportunidade no CRM ou já foi enriquecida (site ou contato); tudo o
    resto — mesmo com atividade/mensagem/reunião registrada — entraria na
    exclusão. Pedido explícito do usuário em 2026-08-24 pra zerar volume
    de import malfeito; não é o crivo padrão do produto."""
    return PreviaLimpezaLeadsSchema(**conta_service.prever_limpeza_leads_nao_trabalhados(db, tenant_id, usuario))


@router.post(
    "/contas/limpeza-nao-trabalhados",
    response_model=ExcluirContasResponseSchema,
    dependencies=[Depends(exigir_papel("super_admin"))],
)
def executar_limpeza_leads_nao_trabalhados(
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> ExcluirContasResponseSchema:
    """Executa a limpeza pontual descrita em `preview_limpeza_leads_nao_trabalhados`."""
    resultado = conta_service.executar_limpeza_leads_nao_trabalhados(db, tenant_id, ator_id, usuario)
    return ExcluirContasResponseSchema(**resultado)


@router.get("/decisores", response_model=list[DecisorSchema])
def listar_decisores_leads(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
) -> list[DecisorSchema]:
    return conta_service.listar_decisores_leads(db, tenant_id, usuario, vendedor_usuario_id)
