from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_tenant_id, limitar_ia_por_tenant
from app.llm.base import LLMProvider
from app.schemas.agente_corporativo import (
    AprovarPerguntaRequestSchema,
    DefinirModoRequestSchema,
    ModoAgenteSchema,
    PerguntaAgenteSchema,
    PerguntarAgenteRequestSchema,
    RecusarPerguntaRequestSchema,
    TestarAgenteRequestSchema,
    TestarAgenteResponseSchema,
)
from app.models.pergunta_agente_corporativo import PerguntaAgenteCorporativo
from app.services import agente_corporativo_service
from app.services.sinal_oportunidade_service import nome_empresa

router = APIRouter(prefix="/agente-corporativo", tags=["agente-corporativo"])


def _serializar(db: Session, perguntas: list[PerguntaAgenteCorporativo]) -> list[PerguntaAgenteSchema]:
    resultado = []
    for pergunta in perguntas:
        dados = PerguntaAgenteSchema.model_validate(pergunta).model_dump()
        dados["tenant_id_alvo_nome"] = nome_empresa(db, pergunta.tenant_id_alvo)
        dados["tenant_id_perguntante_nome"] = nome_empresa(db, pergunta.tenant_id_perguntante)
        resultado.append(PerguntaAgenteSchema(**dados))
    return resultado


@router.get("/modo", response_model=ModoAgenteSchema)
def obter_modo(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ModoAgenteSchema:
    return ModoAgenteSchema(modo=agente_corporativo_service.obter_modo(db, tenant_id))


@router.put("/modo", response_model=ModoAgenteSchema)
def definir_modo(
    dados: DefinirModoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ModoAgenteSchema:
    configuracao = agente_corporativo_service.definir_modo(db, tenant_id, ator_id, dados.modo)
    return ModoAgenteSchema(modo=configuracao.modo)


@router.post("/testar", response_model=TestarAgenteResponseSchema, dependencies=[Depends(limitar_ia_por_tenant())])
def testar_agente(
    dados: TestarAgenteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> TestarAgenteResponseSchema:
    return TestarAgenteResponseSchema(
        **agente_corporativo_service.testar_internamente(db, tenant_id, dados.pergunta, llm)
    )


@router.post(
    "/perguntar", response_model=PerguntaAgenteSchema, status_code=201, dependencies=[Depends(limitar_ia_por_tenant())]
)
def perguntar(
    dados: PerguntarAgenteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> PerguntaAgenteSchema:
    registro = agente_corporativo_service.perguntar(db, tenant_id, ator_id, dados.tenant_id_alvo, dados.pergunta, llm)
    return _serializar(db, [registro])[0]


@router.get("/pendentes", response_model=list[PerguntaAgenteSchema])
def listar_pendentes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[PerguntaAgenteSchema]:
    return _serializar(db, agente_corporativo_service.listar_pendentes(db, tenant_id))


@router.post("/pendentes/{pergunta_id}/aprovar", response_model=PerguntaAgenteSchema)
def aprovar(
    pergunta_id: int,
    dados: AprovarPerguntaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PerguntaAgenteSchema:
    registro = agente_corporativo_service.aprovar(db, tenant_id, ator_id, pergunta_id, dados.resposta_final)
    return _serializar(db, [registro])[0]


@router.post("/pendentes/{pergunta_id}/recusar", response_model=PerguntaAgenteSchema)
def recusar(
    pergunta_id: int,
    dados: RecusarPerguntaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> PerguntaAgenteSchema:
    registro = agente_corporativo_service.recusar(db, tenant_id, ator_id, pergunta_id, dados.motivo)
    return _serializar(db, [registro])[0]


@router.get("/minhas-perguntas", response_model=list[PerguntaAgenteSchema])
def listar_minhas_perguntas(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[PerguntaAgenteSchema]:
    return _serializar(db, agente_corporativo_service.listar_minhas_perguntas(db, tenant_id))
