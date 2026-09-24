from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_llm_provider, get_tenant_id, limitar_ia_por_tenant
from app.llm.base import LLMProvider
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.negocio import Negocio
from app.schemas.conta import ContaSchema
from app.schemas.crm import (
    AtividadeSchema,
    AtualizarNegocioRequestSchema,
    CancelarClienteRequestSchema,
    CriarNegocioRequestSchema,
    CustoAquisicaoSchema,
    DashboardAtividadeSchema,
    DashboardEconomiaSchema,
    DashboardFlywheelSchema,
    DashboardFunilSchema,
    DefinirCustoAquisicaoRequestSchema,
    CriarEstagioRequestSchema,
    DefinirEstagioRequestSchema,
    EstagioFunilSchema,
    ImportarNegociosRequestSchema,
    ImportarNegociosResponseSchema,
    MeetingBriefSchema,
    MoverEstagioRequestSchema,
    NegocioSchema,
    PropostaNegocioSchema,
    RegistrarAtividadeRequestSchema,
    ReordenarEstagiosRequestSchema,
    VendedorComContasSchema,
)
from app.schemas.template_proposta import GerarPropostaRequestSchema
from app.services import crm_service, proposta_service, template_proposta_service

router = APIRouter(prefix="/crm", tags=["crm"])


def _serializar_negocios(db: Session, tenant_id: str, negocios: list[Negocio]) -> list[NegocioSchema]:
    """Empresa e contato responsável não são colunas de `Negocio` — busca
    em lote (sem N+1) pra o Kanban não precisar de um fetch por card."""
    conta_ids = {n.conta_id for n in negocios}
    decisor_ids = {n.decisor_id for n in negocios if n.decisor_id is not None}
    contas = {c.id: c for c in db.query(Conta).filter(Conta.id.in_(conta_ids)).all()} if conta_ids else {}
    decisores = {d.id: d for d in db.query(Decisor).filter(Decisor.id.in_(decisor_ids)).all()} if decisor_ids else {}

    resultado = []
    for negocio in negocios:
        conta = contas.get(negocio.conta_id)
        decisor = decisores.get(negocio.decisor_id) if negocio.decisor_id else None
        dados = NegocioSchema.model_validate(negocio).model_dump()
        dados["conta_nome"] = (conta.nome_fantasia or conta.nome) if conta else ""
        dados["decisor_nome"] = decisor.nome if decisor else None
        resultado.append(NegocioSchema(**dados))
    return resultado


@router.get("/estagios", response_model=list[EstagioFunilSchema])
def listar_estagios(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[EstagioFunilSchema]:
    """Funil de vendas configurável por tenant (Onda B)."""
    return crm_service.listar_estagios(db, tenant_id)


@router.post(
    "/estagios",
    response_model=EstagioFunilSchema,
    status_code=201,
    dependencies=[Depends(exigir_papel("super_admin", "admin"))],
)
def criar_estagio(
    dados: CriarEstagioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> EstagioFunilSchema:
    """"Editar Funil" — cria uma fila nova além das 5 padrão, restrito a
    admin/super_admin."""
    return crm_service.criar_estagio(db, tenant_id, ator_id, dados.nome, dados.tipo)


@router.put(
    "/estagios/{estagio_id}",
    response_model=EstagioFunilSchema,
    dependencies=[Depends(exigir_papel("super_admin", "admin"))],
)
def definir_estagio(
    estagio_id: int,
    dados: DefinirEstagioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> EstagioFunilSchema:
    """"Editar Funil" — renomeia/reconfigura uma fila existente,
    restrito a admin/super_admin (antes desta entrega, qualquer
    usuário autenticado do tenant conseguia chamar esta rota)."""
    return crm_service.definir_estagio(db, tenant_id, ator_id, estagio_id, dados.nome, dados.ordem, dados.tipo)


@router.delete(
    "/estagios/{estagio_id}",
    status_code=204,
    dependencies=[Depends(exigir_papel("super_admin", "admin"))],
)
def excluir_estagio(
    estagio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    """"Editar Funil" — exclui uma fila, restrito a admin/super_admin.
    Recusa se houver negócio nela ou se for a última fila "aberto"."""
    crm_service.excluir_estagio(db, tenant_id, ator_id, estagio_id)


@router.post(
    "/estagios/reordenar",
    response_model=list[EstagioFunilSchema],
    dependencies=[Depends(exigir_papel("super_admin", "admin"))],
)
def reordenar_estagios(
    dados: ReordenarEstagiosRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> list[EstagioFunilSchema]:
    """"Editar Funil" — reordena as filas do funil, restrito a
    admin/super_admin. `ordem_ids` precisa conter exatamente as filas
    atuais do tenant, na nova ordem desejada."""
    return crm_service.reordenar_estagios(db, tenant_id, ator_id, dados.ordem_ids)


@router.get("/negocios", response_model=list[NegocioSchema])
def listar_negocios(
    estagio_id: int | None = None,
    vendedor_usuario_id: int | None = None,
    conta_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[NegocioSchema]:
    """O "kanban de clientes" (Onda B)."""
    negocios = crm_service.listar_negocios(db, tenant_id, estagio_id, vendedor_usuario_id, conta_id)
    return _serializar_negocios(db, tenant_id, negocios)


@router.post("/negocios", response_model=NegocioSchema, status_code=201)
def criar_negocio(
    dados: CriarNegocioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> NegocioSchema:
    negocio = crm_service.criar_negocio(
        db,
        tenant_id,
        ator_id,
        dados.conta_id,
        dados.decisor_id,
        dados.nome,
        dados.valor,
        dados.probabilidade,
        dados.vendedor_usuario_id,
        dados.estagio_id,
        dados.oferta_id,
    )
    return _serializar_negocios(db, tenant_id, [negocio])[0]


@router.post(
    "/negocios/importar",
    response_model=ImportarNegociosResponseSchema,
    dependencies=[Depends(exigir_papel("super_admin", "admin"))],
)
def importar_negocios(
    dados: ImportarNegociosRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ImportarNegociosResponseSchema:
    """Import em lote de oportunidades vindas de outra plataforma — o
    mapeamento de coluna do CSV acontece no frontend (raio-X 2026-09-14)."""
    return ImportarNegociosResponseSchema(**crm_service.importar_negocios(db, tenant_id, ator_id, dados.linhas))


@router.get("/negocios/exportar.csv", dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def exportar_negocios(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    """CSV com todas as oportunidades do tenant — para o cliente levar seu
    histórico embora ao migrar para outra plataforma (raio-X 2026-09-14)."""
    conteudo = crm_service.exportar_negocios_csv(db, tenant_id)
    return Response(
        content=conteudo,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=oportunidades.csv"},
    )


@router.put("/negocios/{negocio_id}", response_model=NegocioSchema)
def atualizar_negocio(
    negocio_id: int,
    dados: AtualizarNegocioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> NegocioSchema:
    negocio = crm_service.atualizar_negocio(
        db, tenant_id, ator_id, negocio_id, dados.nome, dados.valor, dados.probabilidade, dados.decisor_id, dados.oferta_id
    )
    return _serializar_negocios(db, tenant_id, [negocio])[0]


@router.post(
    "/negocios/{negocio_id}/meeting-brief",
    response_model=MeetingBriefSchema,
    dependencies=[Depends(limitar_ia_por_tenant())],
)
def gerar_meeting_brief(
    negocio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> MeetingBriefSchema:
    """Meeting Agent (master prompt §32, Fase 6B)."""
    return MeetingBriefSchema(**crm_service.gerar_meeting_brief(db, tenant_id, ator_id, negocio_id, llm))


@router.delete("/negocios/{negocio_id}", status_code=204)
def excluir_negocio(
    negocio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> None:
    crm_service.excluir_negocio(db, tenant_id, ator_id, negocio_id)


@router.put("/negocios/{negocio_id}/estagio", response_model=NegocioSchema)
def mover_estagio(
    negocio_id: int,
    dados: MoverEstagioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> NegocioSchema:
    """Arrastar no kanban — ganho marca a conta como cliente, perdido grava o motivo (Onda B)."""
    negocio = crm_service.mover_estagio(db, tenant_id, ator_id, negocio_id, dados.estagio_id, dados.motivo_perda)
    return _serializar_negocios(db, tenant_id, [negocio])[0]


@router.post("/negocios/{negocio_id}/atividades", response_model=AtividadeSchema, status_code=201)
def registrar_atividade(
    negocio_id: int,
    dados: RegistrarAtividadeRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> AtividadeSchema:
    return crm_service.registrar_atividade(db, tenant_id, ator_id, negocio_id, dados.tipo, dados.descricao)


@router.get("/negocios/{negocio_id}/atividades", response_model=list[AtividadeSchema])
def listar_atividades(
    negocio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[AtividadeSchema]:
    return crm_service.listar_atividades(db, tenant_id, negocio_id)


@router.post("/negocios/{negocio_id}/propostas", response_model=PropostaNegocioSchema, status_code=201)
async def anexar_proposta(
    negocio_id: int,
    arquivo: UploadFile = File(...),
    nome: str | None = Form(None),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PropostaNegocioSchema:
    conteudo = await arquivo.read()
    return proposta_service.anexar(
        db,
        tenant_id,
        ator_id,
        negocio_id,
        arquivo.filename or "proposta",
        arquivo.content_type or "",
        conteudo,
        nome=nome,
    )


@router.get("/negocios/{negocio_id}/propostas", response_model=list[PropostaNegocioSchema])
def listar_propostas(
    negocio_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[PropostaNegocioSchema]:
    return proposta_service.listar(db, tenant_id, negocio_id)


@router.get("/negocios/{negocio_id}/propostas/{proposta_id}/download")
def baixar_proposta(
    negocio_id: int,
    proposta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    proposta = proposta_service.obter(db, tenant_id, negocio_id, proposta_id)
    return Response(
        content=proposta.conteudo,
        media_type=proposta.tipo_mime,
        headers={"Content-Disposition": f'attachment; filename="{proposta.nome_arquivo}"'},
    )


@router.post("/negocios/{negocio_id}/propostas/gerar", response_model=PropostaNegocioSchema, status_code=201)
def gerar_proposta(
    negocio_id: int,
    dados: GerarPropostaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PropostaNegocioSchema:
    itens_produtos = [item.model_dump() for item in dados.itens_produtos] if dados.itens_produtos is not None else [
        {"descricao": item.descricao, "valor": item.valor}
        for item in template_proposta_service.listar_itens(db, tenant_id, "produto")
    ]
    itens_servicos = [item.model_dump() for item in dados.itens_servicos] if dados.itens_servicos is not None else [
        {"descricao": item.descricao, "valor": item.valor}
        for item in template_proposta_service.listar_itens(db, tenant_id, "servico")
    ]
    conteudo = template_proposta_service.gerar_pdf(
        db,
        tenant_id,
        negocio_id,
        itens_produtos,
        itens_servicos,
        texto_introdutorio=dados.texto_introdutorio,
        termo_aceite=dados.termo_aceite,
        mostrar_tabela_produtos=dados.mostrar_tabela_produtos,
        mostrar_tabela_servicos=dados.mostrar_tabela_servicos,
    )
    return proposta_service.anexar(
        db,
        tenant_id,
        ator_id,
        negocio_id,
        "proposta.pdf",
        "application/pdf",
        conteudo,
        gerada_automaticamente=True,
        nome=dados.nome,
    )


@router.post("/contas/{conta_id}/cancelar-cliente", response_model=ContaSchema)
def cancelar_cliente(
    conta_id: int,
    dados: CancelarClienteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    """Registra o evento de churn (Onda B)."""
    return crm_service.marcar_cliente_cancelado(db, tenant_id, ator_id, conta_id, dados.motivo)


@router.put("/custo-aquisicao", response_model=CustoAquisicaoSchema)
def definir_custo_aquisicao(
    dados: DefinirCustoAquisicaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CustoAquisicaoSchema:
    return crm_service.definir_custo_aquisicao(db, tenant_id, ator_id, dados.periodo, dados.valor)


@router.get("/dashboard/funil", response_model=DashboardFunilSchema)
def dashboard_funil(
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFunilSchema:
    """Estado atual do funil de vendas — sem filtro de período (o funil
    é uma foto do pipeline agora, não um recorte por data de criação).
    `vendedor_usuario_id` (raio-X 2026-09-24, MAP por vendedor) opcional."""
    return DashboardFunilSchema(**crm_service.dashboard_funil(db, tenant_id, vendedor_usuario_id))


@router.get("/dashboard/atividade", response_model=DashboardAtividadeSchema)
def dashboard_atividade(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardAtividadeSchema:
    return DashboardAtividadeSchema(**crm_service.dashboard_atividade(db, tenant_id, data_inicio, data_fim))


@router.get("/dashboard/economia", response_model=DashboardEconomiaSchema)
def dashboard_economia(
    periodo: str,
    vendedor_usuario_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardEconomiaSchema:
    """LTV, CAC e Churn do período "YYYY-MM" (Onda B). `vendedor_usuario_id`
    (raio-X 2026-09-24, MAP por vendedor) opcional — `cac`/`roi` sempre
    `None` quando escopado (ver `crm_service.dashboard_economia`)."""
    return DashboardEconomiaSchema(**crm_service.dashboard_economia(db, tenant_id, periodo, vendedor_usuario_id))


@router.get("/vendedores-com-contas", response_model=list[VendedorComContasSchema])
def listar_vendedores_com_contas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[VendedorComContasSchema]:
    """Árvore vendedor → contas (raio-X 2026-09-24, MAP por vendedor)."""
    return [VendedorComContasSchema(**item) for item in crm_service.listar_vendedores_com_contas(db, tenant_id)]


@router.get("/dashboard/flywheel", response_model=DashboardFlywheelSchema)
def dashboard_flywheel(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFlywheelSchema:
    """CRM (novo) + PREDATOR (já existente) num único payload (Onda B)."""
    return DashboardFlywheelSchema(**crm_service.dashboard_flywheel(db, tenant_id))
