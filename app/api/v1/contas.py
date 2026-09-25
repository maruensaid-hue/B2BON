from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ator_id,
    get_db,
    get_graph_client,
    get_llm_provider,
    get_tenant_id,
    limitar_ia_por_tenant,
)
from app.graph.client import Neo4jClient
from app.llm.base import LLMProvider
from app.models.decisor import Decisor
from app.schemas.conta import (
    AtualizarContaRequestSchema,
    ContaSchema,
    CriarContaManualRequestSchema,
    DefinirProximoPassoRequestSchema,
    DescartarContaRequestSchema,
    EstrategiaVendaSchema,
    GrafoContaResponseSchema,
)
from app.schemas.crm import AtividadeSchema
from app.schemas.decisor import (
    AtualizarDecisorRequestSchema,
    ConfirmarPapelDecisorRequestSchema,
    DecisorCreateSchema,
    DecisorSchema,
)
from app.services import (
    atividade_service,
    conta_service,
    descarte_service,
    linkedin_conexao_service,
    optout_service,
)

router = APIRouter(tags=["contas"])


def _serializar_decisores_com_linkedin(
    db: Session, tenant_id: str, conta_id: int, ator_id: str | None, decisores: list[Decisor]
) -> list[DecisorSchema]:
    conta = conta_service.obter(db, tenant_id, conta_id)
    usuario_id = conta.vendedor_usuario_id or (int(ator_id) if ator_id else None)
    resultado = []
    for decisor in decisores:
        dados = DecisorSchema.model_validate(decisor).model_dump()
        dados["linkedin_conectado"] = (
            linkedin_conexao_service.esta_conectado(db, tenant_id, usuario_id, decisor)
            if usuario_id is not None
            else False
        )
        # Stakeholder Map (master prompt §27, §56, Fase 5B) — sugestão
        # sempre recalculada a partir do cargo atual, nunca persistida.
        dados["papel_sugerido"] = conta_service.sugerir_papel_comite_compra(decisor.cargo)
        resultado.append(DecisorSchema(**dados))
    return resultado


@router.post("/icp/{icp_id}/contas", response_model=ContaSchema, status_code=201)
def criar_conta_manual(
    icp_id: int,
    dados: CriarContaManualRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    """Cadastro avulso de conta pelo CRM — cliente que chegou por indicação
    ou inbound, sem passar pela geração de lista do PREDATOR."""
    return conta_service.criar_manual(db, tenant_id, ator_id, icp_id, dados.nome, dados.cnpj, dados.dominio)


@router.get("/icp/{icp_id}/contas", response_model=list[ContaSchema])
def listar_contas_do_icp(
    icp_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ContaSchema]:
    return conta_service.listar_por_icp(db, tenant_id, icp_id)


@router.get("/contas", response_model=list[ContaSchema])
def listar_todas_as_contas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ContaSchema]:
    """Toda conta do tenant, com ou sem ICP — usado pelo seletor "conta
    existente" ao criar um negócio no Kanban."""
    return conta_service.listar_todas(db, tenant_id)


@router.get("/contas/{conta_id}", response_model=ContaSchema)
def obter_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    return conta_service.obter(db, tenant_id, conta_id)


@router.put("/contas/{conta_id}", response_model=ContaSchema)
def atualizar_conta(
    conta_id: int,
    dados: AtualizarContaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    return conta_service.atualizar(
        db, tenant_id, ator_id, conta_id, dados.nome, dados.cnpj, dados.nome_fantasia, dados.dominio,
        dados.segmento, dados.porte, dados.regiao, dados.resumo_site, dados.observacoes,
    )


@router.put("/contas/{conta_id}/proximo-passo", response_model=ContaSchema)
def definir_proximo_passo(
    conta_id: int,
    dados: DefinirProximoPassoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    return conta_service.definir_proximo_passo(
        db, tenant_id, ator_id, conta_id, dados.proximo_passo, dados.proximo_passo_em
    )


@router.get("/contas/{conta_id}/decisores", response_model=list[DecisorSchema])
def listar_decisores_da_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> list[DecisorSchema]:
    decisores = conta_service.decisores_da_conta(db, conta_id)
    return _serializar_decisores_com_linkedin(db, tenant_id, conta_id, ator_id, decisores)


@router.put("/contas/{conta_id}/decisores/{decisor_id}", response_model=DecisorSchema)
def atualizar_decisor(
    conta_id: int,
    decisor_id: int,
    dados: AtualizarDecisorRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> DecisorSchema:
    return conta_service.atualizar_decisor(
        db, tenant_id, ator_id, conta_id, decisor_id, dados.nome, dados.cargo, dados.email, dados.telefone,
        dados.linkedin_url, dados.conta_id,
    )


@router.post("/contas/{conta_id}/decisores/{decisor_id}/papel", response_model=DecisorSchema)
def confirmar_papel_decisor(
    conta_id: int,
    decisor_id: int,
    dados: ConfirmarPapelDecisorRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> DecisorSchema:
    """Stakeholder Map (master prompt §27, §56, Fase 5B) — confirmação
    humana de um papel no comitê de compra."""
    decisor = conta_service.confirmar_papel_decisor(db, tenant_id, ator_id, conta_id, decisor_id, dados.papel)
    return _serializar_decisores_com_linkedin(db, tenant_id, conta_id, ator_id, [decisor])[0]


@router.post("/contas/{conta_id}/decisores/{decisor_id}/suprimir")
def suprimir_decisor(
    conta_id: int,
    decisor_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> dict:
    """"Excluir contato" no Relatório de Entrega (raio-X 2026-09-16) —
    reaproveita a supressão já usada no opt-out (cancela mensagens
    pendentes, marca `Decisor.suprimido_em`) em vez de criar exclusão de
    decisor isolado nova; exclusão de conta/decisor continua
    deliberadamente restrita."""
    return optout_service.processar(db, tenant_id, decisor_id, origem="manual")


@router.post(
    "/contas/{conta_id}/estrategia-venda",
    response_model=EstrategiaVendaSchema,
    dependencies=[Depends(limitar_ia_por_tenant())],
)
def sugerir_estrategia_venda(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> EstrategiaVendaSchema:
    """Sales Strategy Agent (master prompt §29, Fase 6C)."""
    return EstrategiaVendaSchema(**conta_service.sugerir_estrategia_venda(db, tenant_id, conta_id, llm))


@router.post("/contas/{conta_id}/decisores", response_model=DecisorSchema, status_code=201)
def criar_decisor(
    conta_id: int,
    dados: DecisorCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    graph: Neo4jClient = Depends(get_graph_client),
) -> DecisorSchema:
    return conta_service.criar_decisor_manual(db, tenant_id, ator_id, conta_id, dados, graph)


@router.get("/contas/{conta_id}/grafo", response_model=GrafoContaResponseSchema)
def grafo_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    graph: Neo4jClient = Depends(get_graph_client),
) -> GrafoContaResponseSchema:
    return GrafoContaResponseSchema(**conta_service.grafo(db, tenant_id, conta_id, graph))


@router.get("/contas/{conta_id}/atividades", response_model=list[AtividadeSchema])
def listar_atividades_da_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[AtividadeSchema]:
    conta_service.obter(db, tenant_id, conta_id)
    return atividade_service.listar_por_conta(db, tenant_id, conta_id)


@router.post("/contas/{conta_id}/priorizar", response_model=ContaSchema)
def priorizar_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    """Marca a conta como prioritária (E2-H4)."""
    return descarte_service.priorizar(db, tenant_id, ator_id, conta_id)


@router.post("/contas/{conta_id}/descartar", response_model=ContaSchema)
def descartar_conta(
    conta_id: int,
    dados: DescartarContaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    """Marca a conta como descartada, com motivo obrigatório (E2-H4)."""
    return descarte_service.descartar(db, tenant_id, ator_id, conta_id, dados.motivo)


@router.delete("/contas/{conta_id}", status_code=204)
def excluir_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> Response:
    """Apaga a conta de verdade (não confundir com descartar) — só
    permite se a conta ainda não tiver nenhum sinal de trabalho real
    (negócio, mensagem, reunião etc.); pensado pra corrigir uma
    importação de planilha malfeita e poder reimportar do zero."""
    conta_service.excluir(db, tenant_id, ator_id, conta_id)
    return Response(status_code=204)


@router.get("/contas/{conta_id}/export/pdf")
def exportar_conta_pdf(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    conteudo_pdf = conta_service.exportar_pdf(db, tenant_id, conta_id)
    return Response(content=conteudo_pdf, media_type="application/pdf")
