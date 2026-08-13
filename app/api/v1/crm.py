from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_tenant_id
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
    DefinirEstagioRequestSchema,
    EstagioFunilSchema,
    MoverEstagioRequestSchema,
    NegocioSchema,
    PropostaNegocioSchema,
    RegistrarAtividadeRequestSchema,
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


@router.put("/estagios/{estagio_id}", response_model=EstagioFunilSchema)
def definir_estagio(
    estagio_id: int,
    dados: DefinirEstagioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> EstagioFunilSchema:
    return crm_service.definir_estagio(db, tenant_id, ator_id, estagio_id, dados.nome, dados.ordem, dados.tipo)


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
    )
    return _serializar_negocios(db, tenant_id, [negocio])[0]


@router.put("/negocios/{negocio_id}", response_model=NegocioSchema)
def atualizar_negocio(
    negocio_id: int,
    dados: AtualizarNegocioRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> NegocioSchema:
    negocio = crm_service.atualizar_negocio(
        db, tenant_id, ator_id, negocio_id, dados.nome, dados.valor, dados.probabilidade, dados.decisor_id
    )
    return _serializar_negocios(db, tenant_id, [negocio])[0]


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
    conteudo = template_proposta_service.gerar_pdf(db, tenant_id, negocio_id, itens_produtos, itens_servicos)
    return proposta_service.anexar(
        db,
        tenant_id,
        ator_id,
        negocio_id,
        "proposta.pdf",
        "application/pdf",
        conteudo,
        gerada_automaticamente=True,
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
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFunilSchema:
    return DashboardFunilSchema(**crm_service.dashboard_funil(db, tenant_id, data_inicio, data_fim))


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
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardEconomiaSchema:
    """LTV, CAC e Churn do período "YYYY-MM" (Onda B)."""
    return DashboardEconomiaSchema(**crm_service.dashboard_economia(db, tenant_id, periodo))


@router.get("/dashboard/flywheel", response_model=DashboardFlywheelSchema)
def dashboard_flywheel(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DashboardFlywheelSchema:
    """CRM (novo) + PREDATOR (já existente) num único payload (Onda B)."""
    return DashboardFlywheelSchema(**crm_service.dashboard_flywheel(db, tenant_id))
